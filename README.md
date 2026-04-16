
# Welcome to your CDK Python project!

This is a blank project for CDK development with Python.

The `cdk.json` file tells the CDK Toolkit how to execute your app.

This project is set up like a standard Python project.  The initialization
process also creates a virtualenv within this project, stored under the `.venv`
directory.  To create the virtualenv it assumes that there is a `python3`
(or `python` for Windows) executable in your path with access to the `venv`
package. If for any reason the automatic creation of the virtualenv fails,
you can create the virtualenv manually.

To manually create a virtualenv on MacOS and Linux:

```
$ python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
$ source .venv/bin/activate
```

If you are a Windows platform, you would activate the virtualenv like this:

```
% .venv\Scripts\activate.bat
```

Once the virtualenv is activated, you can install the required dependencies.

```
$ pip install -r requirements.txt
```

At this point you can now synthesize the CloudFormation template for this code.

```
$ cdk synth
```

To add additional dependencies, for example other CDK libraries, just add
them to your `requirements.txt` file and rerun the `python -m pip install -r requirements.txt`
command.

## Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

Enjoy!

## Architecture Diagram

```mermaid
flowchart LR
  U[User]
  FE[Frontend Web App]
  APIGW[API Gateway HTTP API]
  UL[Upload Lambda]
  QL[Query Lambda]
  S3[(S3 Documents Bucket)]
  DDB[(DynamoDB Results Table)]
  CACHE[(In-memory Cache)]
  SQSE[SQS Extract Queue]
  EL[Extract Lambda]
  SQSP[SQS Process Queue]
  PL[Process Lambda]
  SQSA[SQS Analysis Queue]
  AL[Analysis Lambda]
  SQSS[SQS Storage Queue]
  SL[Storage Lambda]
  CW[(CloudWatch Logs)]

  U --> FE
  FE -->|POST /upload| APIGW
  FE -->|GET /results and GET/DELETE /results/{id}| APIGW
  APIGW --> UL
  UL -->|Presigned URL| FE
  FE -->|PUT file| S3

  S3 -->|Object created event| SQSE
  SQSE --> EL
  EL --> SQSP
  SQSP --> PL
  PL --> SQSA
  SQSA --> AL
  AL --> SQSS
  SQSS --> SL
  SL -->|Write result and tag index| DDB

  APIGW --> QL
  QL -->|List/detail read and metadata delete| DDB
  QL -->|Cache-aside detail lookup| CACHE
  QL -->|Delete object| S3

  UL -. logs .-> CW
  EL -. logs .-> CW
  PL -. logs .-> CW
  AL -. logs .-> CW
  SL -. logs .-> CW
  QL -. logs .-> CW
```
