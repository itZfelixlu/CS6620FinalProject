
## Architecture Diagram

Uploads use **two hops**: the browser calls **API Gateway → Upload Lambda** only to get a **presigned URL**; the **file bytes never pass through** Upload Lambda or Query Lambda. The browser then **PUTs directly to S3**. Query Lambda is for **listing / detail / delete**, not for the presigned upload step.


```mermaid
%%{init: {"theme":"base","flowchart": {"nodeSpacing": 18, "rankSpacing": 18, "curve": "linear"}, "themeVariables": {"fontSize": "13px", "edgeLabelBackground":"#ffffff", "primaryTextColor":"#111111", "lineColor":"#555555"}} }%%
flowchart TB
  U[User]
  FE[Frontend Web App]
  APIGW[API Gateway]
  UL[Upload Lambda]
  QL[Query Lambda]
  CACHE[(In-memory cache)]
  S3[(S3 documents bucket)]
  DDB[(DynamoDB)]
  EB[EventBridge]

  subgraph Pipeline[" "]
    EL[Extract Lambda]
    PL[Process Lambda]
    AL[Analysis Lambda]
    SL[Storage Lambda]
  end

  subgraph SQS[" "]
    direction TB
    SQSE[Extract queue]
    SQSP[Process queue]
    SQSA[Analysis queue]
    SQSS[Storage queue]
  end

  U --> FE

  subgraph UploadPath[" "]
    FE -->|POST /upload| APIGW
    APIGW --> UL
    UL -->|JSON presigned URL| FE
  end

  FE -->|PUT file bytes| S3

  subgraph ReadPath[" "]
    FE -->|GET or DELETE /results| APIGW
    APIGW --> QL
    QL --> DDB
    QL --> CACHE
    QL -.->|DELETE removes S3 object| S3
  end

  S3 -.->|Object Created rule| EB
  EB --> SQSE
  SQSE --> EL
  EL --> SQSP
  SQSP --> PL
  PL --> SQSA
  SQSA --> AL
  AL --> SQSS
  SQSS --> SL
  SL --> DDB
```
