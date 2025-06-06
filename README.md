# Spot Interruption Insights - Serverless Event-Driven Spot Interruption Monitoring and Analytics Dashboard

## Introduction 
Spot Interruption Insights is a serverless, event-driven monitoring and analytics dashboard designed to provide near real-time visibility into EC2 Spot Instance interruptions. Spot Instances offer significant cost savings, but their unpredictable interruptions can lead to operational challenges. This solution captures Spot Interruption warnings via Amazon EventBridge, routes them through SQS, and processes them with AWS Lambda, storing rich event data in OpenSearch for visualization. This dashboard helps teams understand interruption patterns, improve capacity planning, design fallback mechanisms or diversify workloads more effectively, and make informed workload placement decisions.


## Architecture

![Diagram](/images/spot-interruption-insights.drawio.png)

## Solution Overview
The architecture leverages a serverless, event-driven approach utilizing AWS native services for robust interruption monitoring. EC2 Spot interruption notices are captured via an Amazon EventBridge rule and routed to an SQS queue for reliable message handling. A Lambda function processes the events, fetching EC2 instance metadata and Auto Scaling Group (ASG) details by making optimized batch calls to the EC2 and Auto Scaling APIs. This design minimizes throttling risks on the control plane APIs, ensuring scalability. The Lambda function is appropriately configured with batching and concurrency limits to prevent overwhelming the API endpoints and the OpenSearch bulk indexing process. After processing, events are bulk-indexed into Amazon OpenSearch Service, enabling near real-time visibility and analytics. A Dead Letter Queue (DLQ) ensures no data is lost in case of failures, while IAM roles enforce least-privilege access between all components.

OpenSearch is deployed within the private subnets of a VPC, ensuring it is not publicly accessible. Access to OpenSearch Dashboards is routed through an Application Load Balancer (ALB) configured with an HTTPS listener, which forwards traffic to an NGINX proxy running on EC2 instances in an Auto Scaling group. This setup provides secure and scalable access. Authentication and authorization are enforced using OpenSearch’s internal user database, ensuring that only authorized users can access the dashboards. 

OpenSearch Dashboards visualize interruption metrics, delivering actionable insights to support effective capacity planning and workload placement.

### Extensibility and Alternative Analytics Tools
While this solution uses Amazon OpenSearch Service for storing and visualizing Spot Interruption data, the architecture is flexible and can be extended to support other analytics and observability platforms. You can modify the Lambda function to forward data to tools such as Amazon QuickSight, Amazon Timestream, Amazon Redshift, or external services like Datadog, Splunk, or Elastic Cloud, depending on your analytics and compliance needs. This enables teams to use their preferred tooling for building visualizations, setting alerts, or integrating with existing dashboards.


## Important Note: 
This application uses multiple AWS services, and there are associated costs beyond the Free Tier usage. Please refer to the [AWS Pricing page](https://aws.amazon.com/pricing/) for specific details. You are accountable for any incurred AWS costs. This example solution does not imply any warranty.

## Requirements
[Create an AWS account](https://portal.aws.amazon.com/gp/aws/developer/registration/index.html) if you do not already have one and log in. The IAM user that you use must have sufficient permissions to make necessary AWS service calls and manage AWS resources.  
[AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) installed and configured  
[Git Installed](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)  
[AWS Serverless Application Model](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html) (AWS SAM) installed  

## Deployment Instructions

Create a new directory, navigate to that directory in a terminal and clone the GitHub repository:  
    
    git clone https://github.com/aws-samples/spot-interruption-insights

Change directory to the solution directory:  
    
    cd spot-interruption-insights

## Prerequisites Checklist for Deployment

This section lists the required setup and configurations **before** deploying the solution stack using AWS SAM.

- **VPC Created -**  Ensure a VPC exists with DNS hostnames and DNS resolution **enabled**. You will need the VPC ID during deployment
- **Public Subnets (2 or more) -** Configure **two or more** public subnet IDs from **different Availability Zones**.
- **Private Subnets (2 or more) -**  Configure **two or more** private subnet IDs from **different Availability Zones**.
- **Outbound Internet Access for Private Subnets -**  Ensure NAT Gateway access as nginx proxy will be installed on EC2 instance in private subnet.
- **ALB Access -** CIDR IP range allowed to access ALB (e.g., `1.2.3.4/32`). This is for accessing the dashboard.
- **Certificate ARN for ALB HTTPS Listner -** To configure HTTPS listener.     
- **AMIId -** Valid EC2 AMI ID for the region.  

Before deploying the solution, ensure that the required Lambda layer containing the requests_aws4auth package is published. This package is essential for AWS request signing, allowing the Lambda function to authenticate API calls made to AWS services such as EC2 and OpenSearch.

To use the layer in your Lambda function, you need the ARN of the published Lambda layer. If the layer is not already published, follow these steps:

The required Lambda layer, containing the requests_aws4auth package, has already been packaged as **requests_aws4auth-layer.zip** and is available in the layers folder of the solution directory. Run the following command to deploy the Lambda layer

    aws lambda publish-layer-version \
        --layer-name requests_aws4auth_boto3 \
        --description "Custom layer for aws4auth and requests" \
        --zip-file fileb://layer/requests_aws4auth-layer.zip \
        --compatible-runtimes python3.13

**IMPORTANT -** Update the Layers section in the SAM template file "template.yaml" with the **LayerVersionArn** ARN obtained in the previous step and save the file.

By default, the layer is private to your account. You can grant access to:

**A Specific Account:**

    aws lambda add-layer-version-permission \
        --layer-name requests_aws4auth-layer \
        --version-number <ver_no> \
        --statement-id allow-account-usage \
        --principal 111122223333 \
        --action lambda:GetLayerVersion

OR

**Your Entire AWS Organization:**

    aws lambda add-layer-version-permission \
        --layer-name requests_aws4auth-layer \
        --version-number <ver_no> \
        --statement-id allow-org-usage \
        --principal "*" \
        --action lambda:GetLayerVersion \
        --organization-id <org-id>

**Replace:**
- '<ver_no>' with the version you want to grant permission to
- 111122223333 with the account ID you want to grant access to
- '<org-id>' with your AWS Org ID (get this from the AWS Organization Console)


**Optional: Verify Permissions**
You can verify who has access:

    aws lambda get-layer-version-policy \
        --layer-name requests_aws4auth-layer \
        --version-number <ver_no>


**Deploy the solution -** From the command line, use AWS SAM to build and deploy the AWS resources as specified in the template.yml file.  

    sam build
    sam deploy --guided

**During the prompts:**

- **Stack Name:** {Enter your preferred stack name}
- **AWS Region:** {Enter your preferred region}
- **Parameter DomainName:** {Enter the name of the OpenSearch domain where the index will be created and data will be pushed for analytics}
- **Parameter MasterUsername:** {Admin username to login to the OpenSearch dashboard}
- **Parameter MasterUserPassword:** {Admin password to login to the OpenSearch dashboard}
- **Parameter IndexName:** {Index name where Spot interrupted instance related data will be pushed}
- **Parameter EventRuleName:** {Amazon EventBridge rule name to capture EC2 Spot interruption notices}
- **Parameter CustomEventRuleName:** {Amazon EventBridge custom rule name to capture EC2 Spot interruption notices. This will be used for verifying the solution}
- **Parameter TargetQueueName:** {EventBridge Rule target SQS name}
- **Parameter SQSDLQQueueName:** {Target SQS Dead Letter Queue name}
- **Parameter LambdaDLQQueueName:** {Lambda Dead Letter Queue name}
- **Parameter VPCId:** {Enter the VPCId where the resources will be deployed}
- **Parameter PublicSubnetIds:** {Enter 2 or more Public SubnetIDs separated by comma}
- **Parameter PrivateSubnetIds:** {Enter 2 or more Private SubnetIDs separated by comma}
- **Parameter RestrictedIPCidr:** {IP address/CIDR for restricting ALB access in CIDR format (e.g., x.x.x.x/32)}
- **Parameter CertificateArn:** {Certificate ARN for configuring ALB HTTPS Listener}
- **Parameter AMIId:** {Valid EC2 AMI ID for the region}
- **Confirm changes before deploy:** Y
- **Allow SAM CLI IAM role creation:** Y  
- **Disable rollback:** N  
- **Save arguments to configuration file:** Y  
- **SAM configuration file:** {Press enter to use default name}  
- **SAM configuration environment:** {Press enter to use default name} 


**Note:-** The complete solution may take approximately 15-20 minutes to deploy successfully. After the deployment is complete, there are a few manual steps that need to be performed to ensure the solution functions as expected. Please find the post-deployment steps listed below.

## Post Deployment Instructions

The following steps need to be performed in the OpenSearch Dashboard after logging in:

Get the DNS Name of the Application Load Balancer endpoint from the deployment output section or the ALB console. Access the OpenSearch dashboard using the ALB DNS name as follows -

http://**[ALB-DNS-NAME]**/_dashboards

You will be redirected to the login page. Log in using the Admin username and password you specified during deployment. 

If this is the first time you are logging in then you may see a Welcome screen. Click on **'Explore on my own'** on the Welcome screen. Click **'Dismiss'** on the next screen. 
If the **'Select your tenant'** dialog appears with **'Global'** preselected, click **'Confirm'**. Otherwise, select **'Global'** first and then and click **'Confirm'**.


### Create Index and attribute mapping

- On the Home screen select the Hamburger Menu icon on the top left and select **'Dev Tools'** at the bottom of the menu.

![Diagram](/images/domain-dashboard-devtools.png)

On the dev tools console, copy the below PUT command and execute the request by clicking on the **'Click to send request'** arrow. **Note-** The index name should match what you entered during the deployment. Please change the name accordingly before creating the index. 

        PUT /spot-interruption-events
        {
            "mappings": {
                "properties": {
                "instance_id": {
                    "type": "keyword"
                },
                "instance_name": {
                    "type": "keyword"
                },
                "instance_type": {
                    "type": "keyword"
                },
                "asg_name": {
                    "type": "keyword"
                },
                "timestamp": {
                    "type": "date"
                },
                "region": {
                    "type": "keyword"
                },
                "availability_zone": {
                    "type": "keyword"
                },
                "private_ip": {
                    "type": "ip"
                },
                "public_ip": {
                    "type": "ip"
                }
                }
            }
        }

Image shared below for reference

![Diagram](/images/domain-dashboard-devtools-2.png)

Confirm if the index got created sucessfully. 

![Diagram](/images/domain-dashboard-index-confirm.png)


### Create Index Pattern and export

Access the Hamburger Menu icon on the top left and select **'Dashboard Management'** from the bottom menu. Click on **'Index Patterns'** and click on **"Create Index Pattern"**

![Diagram](/images/domain-dashboard-createindexpattern.png)

Enter the Index pattern name and click Next step

![Diagram](/images/domain-dashboard-createindexpattern-2.png)

Select **'timestamp'** in primary Timefield and click on **'Create index pattern'**

![Diagram](/images/domain-dashboard-createindexpattern-3.png)

Click on the **star icon** to make the index pattern default

![Diagram](/images/domain-dashboard-indexpattern-default.png)


### Map Lambda execution rule to 'all_access' role to perform operations on the index created

Copy the Lambda execution role ARN from the Lambda function responsible for pushing Spot interruption event data to the OpenSearch index. 

Access the Hamburger Menu icon on the top left and select **'Security'** from the bottom menu.

![Diagram](/images/domain-dashboard-security.png)

Select the **'all_access'** role and Click on **'Mapped User'** tab

![Diagram](/images/domain-dashboard-lambdarole-1.png)

Click on **'Manage Mapping'**

![Diagram](/images/domain-dashboard-lambdarole-2.png)

In the **'Backend roles'** add the Lambda execution role ARN copied above and click on **'Map'**

![Diagram](/images/domain-dashboard-lambdarole-3.png)


You can create more users in the internal database and grant appropriate access to the visualisations and dashboards. The following steps show how to create a read only role and to create a internal user and grant read only access.

### Create a new user and a role with read-only access, then assign the role to the user to grant them read-only access to the Spot Interruption dashboard and visualizations.

Access the Hamburger Menu icon on the top left and select **'Security'** from the bottom menu and select **'Internal Users'** and then select **'Create Internal user'**

![Diagram](/images/domain-dashboard-internaluser-1.png)

Enter username and set a Password

![Diagram](/images/domain-dashboard-internaluser-2.png)

Access the Hamburger Menu icon on the top left and select **'Security'** from the bottom menu and select **'Roles'** and then select **'Create Role'**

Set the **Cluster Permissions** and Index Permissions as seen in the image.

![Diagram](/images/domain-dashboard-internaluser-3.png)

Set the **Tenant Permissions** as seen in the image.

![Diagram](/images/domain-dashboard-internaluser-4.png)

Select **'Mapped Users'** tab and click on **'Manage Mapping'**

![Diagram](/images/domain-dashboard-internaluser-5.png)

Select the user created above in **'Users'** and click on **'Map'**

![Diagram](/images/domain-dashboard-internaluser-6.png)


### Configure and deploy sample visualisations and dashboard

Sample visualizations and a starter dashboard are provided under the data folder in the file named **spot-interruption-dashboard-visualisations.ndjson**.
To import them:

- Navigate to Saved Objects under Dashboard Management in OpenSearch Dashboards.

- Import the spot-interruption-dashboard-visualisations.ndjson file.

- During the import, you may encounter index pattern conflicts. Select the index pattern you created from the dropdown and click **"Confirm all changes"**.

![Diagram](/images/domain-dashboard-importupdatedmessage.png)

Once imported, the sample visualizations and dashboard linked to your index pattern will be available.
You can view the Spot Interruption Dashboard, which includes visualizations based on Availability Zones, Regions, Instance Types, Auto Scaling Groups (ASGs), and Interruptions over time.
You can further customize by creating your own visualizations using the attributes available in the index or by editing/creating new dashboards.

## Testing

A temporary event rule is created during deployment to simulate matching EC2 Spot interruption notices. The rule name will be the name you specified during deployment for parameter **"CustomEventRuleName"**

To verify the solution, you can send sample events as shown in the image below. Replace the instance-id with the actual instance id that is associated with an ASG

![Diagram](/images/eb-test-event.png)

- Once the event is sent successfully, you can log in to the OpenSearch Dashboard and view the **Spot Interruption Dashboard**, where instance-related visualizations should appear. Alternatively, you can navigate to the **"Discover"** section via the hamburger menu to view the raw event details. Ensure the correct index pattern is selected, and adjust the time range if necessary (e.g., to the last 15 minutes) to view the latest data. 


## Sample visualisations and Dashboard

Once the OpenSearch Dashboard is set up and the sample visualizations are imported, you can explore the **"Spot Interruption Dashboard"**, which has been pre-built using the indexed event data. This dashboard provides insights across key dimensions such as Availability Zones, Regions, Instance Types, Auto Scaling Groups, and interruption trends over time. Use it as a starting point to understand the kind of insights possible, and feel free to customize or create new visualizations based on the fields available in the index.

![Diagram](/images/sample-dashboard.png)

## Security and Cost Optimizations
This solution is designed to be secure and cost-efficient by default, but there are some more optimizations you can apply to further reduce cost and enhance security:

### Security Best Practices
- **Amazon Cognito Authentication :** Integrate Amazon Cognito with OpenSearch Dashboards to manage user authentication, enable MFA, and avoid hardcoding admin credentials.

- **Lambda Layer Versioning:** Ensure pinned versions of Lambda Layers are used to avoid unexpected changes.

- **Logging and Threat Detection:** Enable AWS CloudTrail and Amazon GuardDuty to monitor for unauthorized activity or anomalies.


### Cost Optimizations
- **Bulk Indexing with Throttling Controls:** Lambda processes batches and respects throttling limits to avoid excessive OpenSearch usage.

- **Short Retention for CloudWatch Logs:** Tune log retention periods to avoid unnecessary storage costs.

- **Optimize Visualizations:** Design saved visualizations to avoid expensive queries (like wide time ranges and large aggregations).

- **Index Lifecycle Management (ILM) :** Configure ILM policies in OpenSearch to delete or archive older interruption data.

## Conclusion
Spot Interruption Insights empowers teams with the visibility and agility needed to operate confidently with EC2 Spot Instances. By combining a serverless, event-driven architecture with secure, scalable analytics, this solution enables organizations to proactively monitor interruption events, identify trends, and optimize workload strategies for resilience and cost-efficiency. With real-time data at their fingertips, teams can make smarter infrastructure decisions and maximize the benefits of Spot capacity while minimizing disruption risks.

## Cleanup
   
Run the following command to delete the resources 

    sam delete