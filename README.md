
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
  %% ===== Clients =====
  U[User]
  FE[Frontend Web App\n(S3 Static Website)]
  U -->|Use app| FE

  %% ===== API Layer =====
  APIGW[API Gateway\nHTTP API]
  FE -->|POST /upload\nGET /results\nGET/DELETE /results/{id}| APIGW

  %% ===== Upload Path =====
  UL[Upload Lambda]
  S3[(S3 Documents Bucket)]
  APIGW -->|invoke| UL
  UL -->|Return presigned URL| FE
  FE -->|PUT file (pdf/txt)| S3

  %% ===== Event-Driven Pipeline =====
  SQSE[(SQS Extract Queue)]
  EL[Extract Lambda]
  SQSP[(SQS Process Queue)]
  PL[Process Lambda]
  SQSA[(SQS Analysis Queue)]
  AL[Analysis Lambda]
  SQSS[(SQS Storage Queue)]
  SL[Storage Lambda]

  S3 -->|Object-created event| SQSE
  SQSE -->|message| EL
  EL -->|extracted_text| SQSP
  SQSP -->|message| PL
  PL -->|normalized payload| SQSA
  SQSA -->|message| AL
  AL -->|summary + tags| SQSS
  SQSS -->|message| SL

  %% ===== Data Stores =====
  DDB[(DynamoDB Results Table\nMain rows + tag-index rows)]
  SL -->|write result + tag index| DDB

  %% ===== Query + Cache + Delete =====
  QL[Query Lambda]
  CACHE[(In-memory Cache\ncache-aside for detail)]
  APIGW -->|invoke| QL
  QL <-->|read/list/detail/delete metadata| DDB
  QL <-->|GET /results/{id}| CACHE
  QL -->|DELETE object| S3

  %% ===== Observability =====
  CW[(CloudWatch Logs)]
  UL -. logs .-> CW
  EL -. logs .-> CW
  PL -. logs .-> CW
  AL -. logs .-> CW
  SL -. logs .-> CW
  QL -. logs .-> CW
```
