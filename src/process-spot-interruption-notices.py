'''

This code will process the Spot interruption notices in batches, extract ASG and instance metadata 
for each Spot interrupted instance and perform bulk additions to the OpenSearch index.

'''
import time
import boto3
import json
import os
import requests
from requests_aws4auth import AWS4Auth
from datetime import datetime, timezone
from urllib.parse import urljoin
from botocore.exceptions import BotoCoreError, ClientError

# region = "us-east-1"
region = os.environ['AWS_REGION']
print("Current Region - ",region)

# AWS clients
ec2 = boto3.client("ec2", region_name=region)
asg = boto3.client("autoscaling", region_name=region)

# OpenSearch config
OPENSEARCH_HOST = os.environ["OPENSEARCH_HOST"]
OPENSEARCH_INDEX_NAME = os.environ["OPENSEARCH_INDEX_NAME"]

# AWS4Auth setup
session         = boto3.Session()
credentials     = session.get_credentials()

aws_auth    = AWS4Auth(
    credentials.access_key,
    credentials.secret_key,
    region,
    "es",
    session_token=credentials.token
)

'''
# This method will push data to OpenSearch in bulk
def bulk_push_to_opensearch(documents):
    url = urljoin(OPENSEARCH_HOST, f"{OPENSEARCH_INDEX_NAME}/_bulk")
    headers = {"Content-Type": "application/x-ndjson"}
    payload = "".join(json.dumps({"index": {}}) + "\n" + json.dumps(doc) + "\n" for doc in documents)

    try:
        response = requests.post(url, auth=aws_auth, headers=headers, data=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Bulk indexing failed: {e}")

'''

# This method will push data to OpenSearch in bulk
# bulk push with error checking and retry
def bulk_push_to_opensearch(documents, max_retries=3):
    url = urljoin(OPENSEARCH_HOST, f"{OPENSEARCH_INDEX_NAME}/_bulk")
    headers = {"Content-Type": "application/x-ndjson"}

    payload = "".join(json.dumps({"index": {}}) + "\n" + json.dumps(doc) + "\n" for doc in documents)

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(url, auth=aws_auth, headers=headers, data=payload, timeout=(25, 25))
            response.raise_for_status()
            bulk_response = response.json()

            # Check if any document failed
            if bulk_response.get("errors"):
                failed_docs = []
                for idx, item in enumerate(bulk_response["items"]):
                    if item.get("index", {}).get("error"):
                        print(f"Document {idx} failed: {item['index']['error']}")
                        failed_docs.append(documents[idx])

                if failed_docs:
                    print(f"Retrying {len(failed_docs)} failed documents (attempt {attempt})...")
                    documents = failed_docs
                    payload = "".join(json.dumps({"index": {}}) + "\n" + json.dumps(doc) + "\n" for doc in documents)
                    time.sleep(1 * attempt)  # Exponential backoff
                    continue
            else:
                # All documents indexed successfully
                # print(f"Bulk push successful. {len(documents)} documents indexed.")
                break

        except requests.exceptions.RequestException as e:
            print(f"Bulk indexing request failed: {e}")
            time.sleep(1 * attempt)
        
    else:
        print(f"Bulk indexing failed after {max_retries} retries. {len(documents)} documents lost.")

        
# This method will fetch ASG and Instance metadata in batches 
# and creates documents to be pushed to OpenSearch
def lambda_handler(event, context):
    records = event["Records"]
    raw_instance_ids = []
    interruption_times = {}

    for record in records:
        try:
            body = json.loads(record["body"])
            instance_id = body["detail"]["instance-id"]
            interruption_time = body["time"]
            raw_instance_ids.append(instance_id)
            interruption_times[instance_id] = interruption_time
        except Exception as e:
            print(f"Failed to parse record: {e}")
            

    if not raw_instance_ids:
        print("No valid instance IDs found after parsing.")
        return {"statusCode": 200, "body": "No valid instance IDs found."}

    documents = []

    # Retrieve ASG mappings in batches of 50
    instance_asg_map = {}
    asg_names = set()
    for i in range(0, len(raw_instance_ids), 50):
        batch_ids = raw_instance_ids[i:i + 50]
        try:
            response = asg.describe_auto_scaling_instances(InstanceIds=batch_ids)
            for instance in response.get("AutoScalingInstances", []):
                iid = instance["InstanceId"]
                asg_name = instance["AutoScalingGroupName"]
                instance_asg_map[iid] = asg_name
                asg_names.add(asg_name)
        except Exception as e:
            print(f"ASG batch failed for IDs {batch_ids}: {e}")

    # Only process instances associated with an ASG
    valid_instance_ids = list(instance_asg_map.keys())
    print("Valid instance IDs: " + str(valid_instance_ids))
    
    if not valid_instance_ids:
        print("No instances associated with ASG. Skipping processing.")
        return {"statusCode": 200}

    # Fetch EC2 instance metadata in batches of 100
    instance_meta_map = {}
    for i in range(0, len(valid_instance_ids), 100):
        batch_ids = valid_instance_ids[i:i + 100]
        try:
            response = ec2.describe_instances(InstanceIds=batch_ids)
            for reservation in response.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    try:
                        iid = instance["InstanceId"]
                        name_tag = next((tag["Value"] for tag in instance.get("Tags", []) if tag["Key"] == "Name"), None)
                        instance_meta_map[iid] = {
                            "instance_type": instance.get("InstanceType"),
                            "private_ip": instance.get("PrivateIpAddress"),
                            "public_ip": instance.get("PublicIpAddress"),
                            "instance_name": name_tag,
                            "availability_zone": instance["Placement"]["AvailabilityZone"]
                        }
                    except Exception as e:
                        print(f"Failed to process instance metadata for {instance.get('InstanceId', 'unknown')}: {e}")
        except ClientError as ce:
            if ce.response["Error"]["Code"] == "InvalidInstanceID.NotFound":
                print(f"Some instance IDs not found in batch: {batch_ids}")
            else:
                print(f"EC2 describe_instances failed: {ce}")
        except Exception as e:
            print(f"Error during EC2 metadata fetch for batch {batch_ids}: {e}")

    # Build documents only for instances that have both ASG + metadata
    for instance_id in valid_instance_ids:
        document = {
            "timestamp": interruption_times.get(instance_id),
            "instance_id": instance_id,
            "asg_name": instance_asg_map[instance_id],
            "region": region,
            **instance_meta_map[instance_id],
            "ingested_at": datetime.now(timezone.utc).isoformat()
        }
        documents.append(document)

    if documents:
        bulk_push_to_opensearch(documents)
        
    print(f"Processed {len(documents)} documents")

    return {"statusCode": 200}

