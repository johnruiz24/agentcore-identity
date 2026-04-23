#!/usr/bin/env node
/**
 * BEDROCK AGENTCORE OAUTH2 COMPLETE PLATFORM - CDK STACK
 *
 * THREE-LAYER ARCHITECTURE:
 * 1. IDENTITY SERVICE - OAuth2 authentication with Google Calendar
 * 2. GATEWAY SERVICE - MCP protocol integrator with OAuth2 authorization
 * 3. RUNTIME SERVICE - Google Calendar operations executor
 *
 * 100% Infrastructure as Code via AWS CDK
 * Using actual Bedrock AgentCore constructs
 */

import * as cdk from "aws-cdk-lib";
import { Duration, RemovalPolicy, Tags } from "aws-cdk-lib";
import {
  aws_kms as kms,
  aws_iam as iam,
  aws_dynamodb as dynamodb,
  aws_secretsmanager as secrets,
  aws_s3 as s3,
  aws_logs as logs,
  aws_apigatewayv2 as apigw,
  aws_apigatewayv2_integrations as apigw_integrations,
  aws_lambda as lambda,
} from "aws-cdk-lib";
import { Construct } from "constructs";
import {
  Runtime,
  Gateway,
  Memory,
  AgentRuntimeArtifact,
  RuntimeNetworkConfiguration,
  ProtocolType,
} from "@aws-cdk/aws-bedrock-agentcore-alpha";
import * as fs from "fs";
import * as path from "path";

/**
 * COMPLETE BEDROCK AGENTCORE OAUTH2 PLATFORM STACK
 *
 * STEP-BY-STEP INFRASTRUCTURE DEPLOYMENT:
 * 1. Encryption (KMS)
 * 2. Storage (DynamoDB - credentials, oauth flows, sessions)
 * 3. Secrets (Google OAuth configuration)
 * 4. S3 Buckets (Agent code and artifacts)
 * 5. Logging (CloudWatch)
 * 6. IAM Roles (Identity, Gateway, Runtime service roles)
 * 7. Lambda Functions (Identity, Gateway, Runtime handlers)
 * 8. API Gateway (HTTP API with CORS)
 * 9. Bedrock AgentCore Services (Runtime, Gateway, Memory)
 * 10. CloudFormation Outputs (Cross-stack references)
 * 11. Resource Tags (Service organization)
 */
export class BedrockAgentCoreCompleteStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    console.log("\n" + "=".repeat(140));
    console.log("🚀 BEDROCK AGENTCORE OAUTH2 PLATFORM - COMPLETE CDK DEPLOYMENT");
    console.log("=".repeat(140));

    // ========== STEP 1: ENCRYPTION ==========
    console.log("\n📍 STEP 1: ENCRYPTION - KMS Key Setup\n");
    const kmsKey = this.setupEncryption();

    // ========== STEP 2: STORAGE ==========
    console.log("\n📍 STEP 2: STORAGE - DynamoDB Tables\n");
    const { credentialsTable, oauthFlowsTable, sessionsTable } =
      this.setupStorage(kmsKey);

    // ========== STEP 3: SECRETS ==========
    console.log("\n📍 STEP 3: SECRETS MANAGEMENT - Secrets Manager\n");
    const googleOAuthSecret = this.setupSecrets();

    // ========== STEP 4: S3 CODE BUCKETS ==========
    console.log("\n📍 STEP 4: S3 BUCKETS - Agent Code Storage\n");
    const agentCodeBucket = this.setupS3Buckets(kmsKey);

    // ========== STEP 5: CLOUDWATCH LOGS ==========
    console.log("\n📍 STEP 5: LOGGING - CloudWatch Setup\n");
    const logGroup = this.setupLogging(kmsKey);

    // ========== STEP 6: IAM ROLES ==========
    console.log("\n📍 STEP 6: IAM ROLES - Service Permissions\n");
    const { identityServiceRole, gatewayServiceRole, runtimeServiceRole } =
      this.setupIAMRoles(
        credentialsTable,
        oauthFlowsTable,
        sessionsTable,
        kmsKey,
        googleOAuthSecret,
        logGroup
      );

    // ========== STEP 7: LAMBDA FUNCTIONS ==========
    console.log("\n📍 STEP 7: LAMBDA FUNCTIONS - OAuth2 Handlers\n");
    const { identityFunction, gatewayFunction, runtimeFunction } =
      this.setupLambdaFunctions(
        identityServiceRole,
        gatewayServiceRole,
        runtimeServiceRole,
        credentialsTable,
        oauthFlowsTable,
        sessionsTable,
        kmsKey,
        googleOAuthSecret,
        logGroup
      );

    // ========== STEP 8: API GATEWAY ==========
    console.log("\n📍 STEP 8: API GATEWAY - HTTP API Deployment\n");
    const api = this.setupAPIGateway(
      identityFunction,
      gatewayFunction,
      runtimeFunction
    );

    // ========== STEP 9: BEDROCK AGENTCORE SERVICES ==========
    console.log(
      "\n📍 STEP 9: BEDROCK AGENTCORE - Runtime, Gateway, Memory\n"
    );
    const { identityRuntime, gateway, sessionMemory } =
      this.setupBedrockAgentCore(
        agentCodeBucket,
        identityServiceRole,
        gatewayServiceRole,
        runtimeServiceRole,
        kmsKey,
        googleOAuthSecret
      );

    // ========== STEP 10: OUTPUTS ==========
    console.log("\n📍 STEP 10: OUTPUTS - CloudFormation Exports\n");
    this.setupOutputs(
      api,
      identityFunction,
      gatewayFunction,
      runtimeFunction,
      credentialsTable,
      oauthFlowsTable,
      sessionsTable,
      kmsKey,
      googleOAuthSecret,
      agentCodeBucket,
      logGroup,
      identityRuntime,
      gateway,
      sessionMemory
    );

    // ========== STEP 11: TAGS ==========
    console.log("\n📍 STEP 11: TAGS - Resource Organization\n");
    this.setupTags();

    console.log("\n" + "=".repeat(140));
    console.log("✅ BEDROCK AGENTCORE OAUTH2 PLATFORM STACK COMPLETE");
    console.log("=".repeat(140) + "\n");
  }

  private setupEncryption(): kms.Key {
    console.log("🔐 Creating KMS encryption key for data protection...");

    const kmsKey = new kms.Key(this, "BedrockAgentCoreKMS", {
      enableKeyRotation: true,
      description:
        "KMS key for Bedrock AgentCore OAuth2 - encrypts credentials, OAuth flows, and sessions",
      removalPolicy: RemovalPolicy.RETAIN,
      pendingWindow: Duration.days(7),
    });

    kmsKey.addAlias("alias/bedrock-agentcore-oauth2");

    kmsKey.grantEncryptDecrypt(
      new iam.ServicePrincipal("logs.amazonaws.com")
    );

    console.log(`   ✅ KMS Key ID: ${kmsKey.keyId}`);
    console.log(`   ✅ Alias: alias/bedrock-agentcore-oauth2`);
    console.log(`   ✅ Key Rotation: Enabled (annual)`);

    return kmsKey;
  }

  private setupStorage(kmsKey: kms.Key): {
    credentialsTable: dynamodb.Table;
    oauthFlowsTable: dynamodb.Table;
    sessionsTable: dynamodb.Table;
  } {
    console.log("💾 Creating DynamoDB tables for persistent storage...");

    const credentialsTable = new dynamodb.Table(this, "CredentialsTable", {
      tableName: "bedrock-agentcore-oauth2-creds-final",
      partitionKey: {
        name: "user_id",
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: "credential_id",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kmsKey,
      removalPolicy: RemovalPolicy.RETAIN,
      pointInTimeRecovery: true,
    });

    credentialsTable.addGlobalSecondaryIndex({
      indexName: "credential_id-index",
      partitionKey: {
        name: "credential_id",
        type: dynamodb.AttributeType.STRING,
      },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    console.log(`   ✅ Credentials Table: ${credentialsTable.tableName}`);

    const oauthFlowsTable = new dynamodb.Table(this, "OAuthFlowsTable", {
      tableName: "bedrock-agentcore-oauth2-flows-final",
      partitionKey: {
        name: "flow_id",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kmsKey,
      removalPolicy: RemovalPolicy.RETAIN,
      timeToLiveAttribute: "ttl",
      pointInTimeRecovery: true,
    });

    oauthFlowsTable.addGlobalSecondaryIndex({
      indexName: "state-index",
      partitionKey: {
        name: "state",
        type: dynamodb.AttributeType.STRING,
      },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    console.log(`   ✅ OAuth Flows Table: ${oauthFlowsTable.tableName}`);

    const sessionsTable = new dynamodb.Table(this, "SessionsTable", {
      tableName: "bedrock-agentcore-sessions-final",
      partitionKey: {
        name: "session_id",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kmsKey,
      removalPolicy: RemovalPolicy.RETAIN,
      timeToLiveAttribute: "ttl",
      pointInTimeRecovery: true,
    });

    sessionsTable.addGlobalSecondaryIndex({
      indexName: "user_id-index",
      partitionKey: {
        name: "user_id",
        type: dynamodb.AttributeType.STRING,
      },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    console.log(`   ✅ Sessions Table: ${sessionsTable.tableName}`);

    return { credentialsTable, oauthFlowsTable, sessionsTable };
  }

  private setupSecrets(): secrets.Secret {
    console.log("🔑 Creating Secrets Manager for OAuth2 credentials...");

    const googleOAuthSecret = new secrets.Secret(this, "GoogleOAuthSecret", {
      secretName: "bedrock-agentcore-oauth2/google-oauth",
      description: "Google OAuth2 credentials (client_id, client_secret, redirect_uri)",
      removalPolicy: RemovalPolicy.RETAIN,
    });

    console.log(
      `   ✅ Google OAuth Secret: ${googleOAuthSecret.secretArn}`
    );

    return googleOAuthSecret;
  }

  private setupS3Buckets(kmsKey: kms.Key): s3.Bucket {
    console.log("📦 Creating S3 buckets for agent code storage...");

    const agentCodeBucket = new s3.Bucket(this, "AgentCodeBucket", {
      bucketName: `bedrock-agentcore-code-${this.account}-${this.region}`,
      versioned: true,
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: kmsKey,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    console.log(`   ✅ Agent Code Bucket: ${agentCodeBucket.bucketName}`);

    return agentCodeBucket;
  }

  private setupLogging(kmsKey: kms.Key): logs.LogGroup {
    console.log("📋 Creating CloudWatch log group for Lambda functions...");

    const logGroup = new logs.LogGroup(this, "BedrockAgentCoreLogGroup", {
      logGroupName: "/aws/bedrock-agentcore/oauth2",
      retention: logs.RetentionDays.ONE_MONTH,
      encryptionKey: kmsKey,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    console.log(`   ✅ Log Group: ${logGroup.logGroupName}`);

    return logGroup;
  }

  private setupIAMRoles(
    credentialsTable: dynamodb.Table,
    oauthFlowsTable: dynamodb.Table,
    sessionsTable: dynamodb.Table,
    kmsKey: kms.Key,
    googleOAuthSecret: secrets.Secret,
    logGroup: logs.LogGroup
  ): {
    identityServiceRole: iam.Role;
    gatewayServiceRole: iam.Role;
    runtimeServiceRole: iam.Role;
  } {
    console.log("👤 Creating IAM roles with least-privilege permissions...");

    const identityServiceRole = new iam.Role(this, "IdentityServiceRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      description: "IAM role for Bedrock AgentCore Identity Service",
      roleName: "bedrock-agentcore-identity-service-role",
    });

    identityServiceRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
        ],
        resources: [credentialsTable.tableArn],
      })
    );

    identityServiceRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
        ],
        resources: [oauthFlowsTable.tableArn],
      })
    );

    identityServiceRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"],
        resources: [kmsKey.keyArn],
      })
    );

    identityServiceRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ["secretsmanager:GetSecretValue"],
        resources: [googleOAuthSecret.secretArn],
      })
    );

    identityServiceRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ["logs:CreateLogStream", "logs:PutLogEvents"],
        resources: [logGroup.logGroupArn],
      })
    );

    console.log(`   ✅ Identity Service Role: ${identityServiceRole.roleName}`);

    const gatewayServiceRole = new iam.Role(this, "GatewayServiceRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      description: "IAM role for Bedrock AgentCore Gateway Service",
      roleName: "bedrock-agentcore-gateway-service-role",
    });

    gatewayServiceRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ["dynamodb:GetItem", "dynamodb:Query"],
        resources: [credentialsTable.tableArn],
      })
    );

    gatewayServiceRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
        ],
        resources: [sessionsTable.tableArn],
      })
    );

    gatewayServiceRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ["kms:Decrypt"],
        resources: [kmsKey.keyArn],
      })
    );

    gatewayServiceRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ["logs:CreateLogStream", "logs:PutLogEvents"],
        resources: [logGroup.logGroupArn],
      })
    );

    console.log(`   ✅ Gateway Service Role: ${gatewayServiceRole.roleName}`);

    const runtimeServiceRole = new iam.Role(this, "RuntimeServiceRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      description: "IAM role for Bedrock AgentCore Runtime Service",
      roleName: "bedrock-agentcore-runtime-service-role",
    });

    runtimeServiceRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ["dynamodb:GetItem"],
        resources: [credentialsTable.tableArn],
      })
    );

    runtimeServiceRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
        ],
        resources: [sessionsTable.tableArn],
      })
    );

    runtimeServiceRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ["kms:Decrypt"],
        resources: [kmsKey.keyArn],
      })
    );

    runtimeServiceRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
        ],
        resources: ["arn:aws:bedrock:*::foundation-model/*"],
      })
    );

    runtimeServiceRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ["logs:CreateLogStream", "logs:PutLogEvents"],
        resources: [logGroup.logGroupArn],
      })
    );

    console.log(`   ✅ Runtime Service Role: ${runtimeServiceRole.roleName}`);

    return {
      identityServiceRole,
      gatewayServiceRole,
      runtimeServiceRole,
    };
  }

  private setupLambdaFunctions(
    identityServiceRole: iam.Role,
    gatewayServiceRole: iam.Role,
    runtimeServiceRole: iam.Role,
    credentialsTable: dynamodb.Table,
    oauthFlowsTable: dynamodb.Table,
    sessionsTable: dynamodb.Table,
    kmsKey: kms.Key,
    googleOAuthSecret: secrets.Secret,
    logGroup: logs.LogGroup
  ): {
    identityFunction: lambda.Function;
    gatewayFunction: lambda.Function;
    runtimeFunction: lambda.Function;
  } {
    console.log("⚡ Creating Lambda functions for three-layer architecture...");

    const readLambdaCode = (filename: string): string => {
      const filepath = path.join(
        __dirname,
        `../src/deployment/lambdas/${filename}`
      );
      if (fs.existsSync(filepath)) {
        return fs.readFileSync(filepath, "utf-8");
      }
      return `
def handler(event, context):
    return {
        "statusCode": 500,
        "body": '{"error": "${filename} not found"}'
    }
`;
    };

    const identityFunction = new lambda.Function(
      this,
      "IdentityHandler",
      {
        functionName: "bedrock-agentcore-identity-handler-final",
        runtime: lambda.Runtime.PYTHON_3_11,
        code: lambda.Code.fromInline(readLambdaCode("identity_handler.py")),
        handler: "index.handler",
        role: identityServiceRole,
        environment: {
          CREDENTIALS_TABLE: credentialsTable.tableName,
          OAUTH_FLOWS_TABLE: oauthFlowsTable.tableName,
          KMS_KEY_ID: kmsKey.keyId,
          GOOGLE_SECRET_ARN: googleOAuthSecret.secretArn,
          REGION: this.region,
          LOG_LEVEL: "INFO",
          SERVICE_NAME: "identity",
        },
        timeout: Duration.seconds(60),
        memorySize: 512,
        logGroup: logGroup,
      }
    );

    console.log(`   ✅ Identity Function: ${identityFunction.functionName}`);

    const gatewayFunction = new lambda.Function(this, "GatewayHandler", {
      functionName: "bedrock-agentcore-gateway-handler-final",
      runtime: lambda.Runtime.PYTHON_3_11,
      code: lambda.Code.fromInline(readLambdaCode("gateway_handler.py")),
      handler: "index.handler",
      role: gatewayServiceRole,
      environment: {
        CREDENTIALS_TABLE: credentialsTable.tableName,
        OAUTH_FLOWS_TABLE: oauthFlowsTable.tableName,
        SESSIONS_TABLE: sessionsTable.tableName,
        KMS_KEY_ID: kmsKey.keyId,
        REGION: this.region,
        LOG_LEVEL: "INFO",
        SERVICE_NAME: "gateway",
      },
      timeout: Duration.seconds(60),
      memorySize: 512,
      logGroup: logGroup,
    });

    console.log(`   ✅ Gateway Function: ${gatewayFunction.functionName}`);

    const runtimeFunction = new lambda.Function(this, "RuntimeHandler", {
      functionName: "bedrock-agentcore-runtime-handler-final",
      runtime: lambda.Runtime.PYTHON_3_11,
      code: lambda.Code.fromInline(readLambdaCode("runtime_handler.py")),
      handler: "index.handler",
      role: runtimeServiceRole,
      environment: {
        CREDENTIALS_TABLE: credentialsTable.tableName,
        SESSIONS_TABLE: sessionsTable.tableName,
        KMS_KEY_ID: kmsKey.keyId,
        REGION: this.region,
        LOG_LEVEL: "INFO",
        SERVICE_NAME: "runtime",
      },
      timeout: Duration.seconds(60),
      memorySize: 512,
      logGroup: logGroup,
    });

    console.log(`   ✅ Runtime Function: ${runtimeFunction.functionName}`);

    return { identityFunction, gatewayFunction, runtimeFunction };
  }

  private setupAPIGateway(
    identityFunction: lambda.Function,
    gatewayFunction: lambda.Function,
    runtimeFunction: lambda.Function
  ): apigw.HttpApi {
    console.log("🌐 Creating HTTP API Gateway with Lambda integrations...");

    const api = new apigw.HttpApi(this, "BedrockAgentCoreAPI", {
      apiName: "bedrock-agentcore-oauth2-api-final",
      description: "Bedrock AgentCore OAuth2 Platform API",
      corsPreflight: {
        allowOrigins: ["*"],
        allowMethods: [
          apigw.CorsHttpMethod.GET,
          apigw.CorsHttpMethod.POST,
          apigw.CorsHttpMethod.PUT,
          apigw.CorsHttpMethod.DELETE,
        ],
        allowHeaders: ["*"],
        maxAge: Duration.days(1),
      },
    });

    console.log(`   ✅ HTTP API: ${api.url}`);

    const identityIntegration =
      new apigw_integrations.HttpLambdaIntegration(
        "IdentityIntegration",
        identityFunction
      );

    const gatewayIntegration =
      new apigw_integrations.HttpLambdaIntegration(
        "GatewayIntegration",
        gatewayFunction
      );

    const runtimeIntegration =
      new apigw_integrations.HttpLambdaIntegration(
        "RuntimeIntegration",
        runtimeFunction
      );

    // Identity Service Routes
    api.addRoutes({
      path: "/oauth/authorize",
      methods: [apigw.HttpMethod.GET],
      integration: identityIntegration,
    });

    api.addRoutes({
      path: "/oauth/callback",
      methods: [apigw.HttpMethod.POST],
      integration: identityIntegration,
    });

    api.addRoutes({
      path: "/oauth/status",
      methods: [apigw.HttpMethod.GET],
      integration: identityIntegration,
    });

    // Gateway Service Routes
    api.addRoutes({
      path: "/gateway/validate",
      methods: [apigw.HttpMethod.POST],
      integration: gatewayIntegration,
    });

    api.addRoutes({
      path: "/gateway/invoke",
      methods: [apigw.HttpMethod.POST],
      integration: gatewayIntegration,
    });

    // Runtime Service Routes
    api.addRoutes({
      path: "/runtime/calendar/events",
      methods: [apigw.HttpMethod.GET],
      integration: runtimeIntegration,
    });

    api.addRoutes({
      path: "/runtime/calendar/create",
      methods: [apigw.HttpMethod.POST],
      integration: runtimeIntegration,
    });

    console.log(`   ✅ API Routes Configured (7 total)`);

    return api;
  }

  private setupBedrockAgentCore(
    agentCodeBucket: s3.Bucket,
    identityServiceRole: iam.Role,
    gatewayServiceRole: iam.Role,
    runtimeServiceRole: iam.Role,
    kmsKey: kms.Key,
    googleOAuthSecret: secrets.Secret
  ): {
    identityRuntime: Runtime;
    gateway: Gateway;
    sessionMemory: Memory;
  } {
    console.log(
      "🛠️  Creating Bedrock AgentCore services (Runtime, Gateway, Memory)...\n"
    );

    // ========== IDENTITY RUNTIME ==========
    console.log("   📌 Creating Identity Runtime (OAuth2 Layer 1)...");

    const identityArtifact = AgentRuntimeArtifact.fromImageUri(
      `${this.account}.dkr.ecr.${this.region}.amazonaws.com/bedrock-agentcore-identity:latest`
    );

    const identityRuntime = new Runtime(this, "IdentityRuntime", {
      runtimeName: "bedrock_agentcore_identity_oauth2",
      executionRole: identityServiceRole,
      agentRuntimeArtifact: identityArtifact,
      networkConfiguration: RuntimeNetworkConfiguration.usingPublicNetwork(),
      description: "Bedrock AgentCore Identity Runtime - Google OAuth2 authentication",
      protocolConfiguration: ProtocolType.HTTP,
      environmentVariables: {
        CREDENTIALS_TABLE: "bedrock-agentcore-oauth2-credentials",
        OAUTH_FLOWS_TABLE: "bedrock-agentcore-oauth2-oauth-flows",
        KMS_KEY_ID: kmsKey.keyId,
        GOOGLE_SECRET_ARN: googleOAuthSecret.secretArn,
        SERVICE_NAME: "identity",
        LOG_LEVEL: "INFO",
      },
      tags: {
        Service: "identity",
        Layer: "1-oauth2",
      },
    });

    identityRuntime.addEndpoint("prod");
    identityRuntime.addEndpoint("staging");

    console.log(`      ✅ Identity Runtime created`);

    // ========== GATEWAY ==========
    console.log("   📌 Creating Gateway (MCP + OAuth2 Layer 2)...");

    const gateway = new Gateway(this, "OAuth2Gateway", {
      gatewayName: "bedrock-agentcore-oauth2-gateway",
      description: "Bedrock AgentCore Gateway - MCP protocol with OAuth2 authorization",
      tags: {
        Service: "gateway",
        Layer: "2-authorization",
      },
    });

    console.log(`      ✅ Gateway created`);

    // ========== MEMORY ==========
    console.log("   📌 Creating Session Memory (Context Storage)...");

    const sessionMemory = new Memory(this, "SessionMemory", {
      memoryName: "bedrock_agentcore_session_memory",
      description: "Session memory for storing conversation context and state",
      expirationDuration: Duration.days(90),
      kmsKey: kmsKey,
      executionRole: runtimeServiceRole,
      tags: {
        Service: "memory",
        Type: "session-storage",
      },
    });

    console.log(`      ✅ Session Memory created`);

    console.log("\n   ✅ All Bedrock AgentCore services deployed");

    return { identityRuntime, gateway, sessionMemory };
  }

  private setupOutputs(
    api: apigw.HttpApi,
    identityFunction: lambda.Function,
    gatewayFunction: lambda.Function,
    runtimeFunction: lambda.Function,
    credentialsTable: dynamodb.Table,
    oauthFlowsTable: dynamodb.Table,
    sessionsTable: dynamodb.Table,
    kmsKey: kms.Key,
    googleOAuthSecret: secrets.Secret,
    agentCodeBucket: s3.Bucket,
    logGroup: logs.LogGroup,
    identityRuntime: Runtime,
    gateway: Gateway,
    sessionMemory: Memory
  ): void {
    console.log("📤 Creating CloudFormation outputs for cross-stack references...");

    new cdk.CfnOutput(this, "APIEndpoint", {
      value: api.url!,
      exportName: "BedrockAgentCoreAPIEndpoint",
    });

    new cdk.CfnOutput(this, "IdentityFunctionArn", {
      value: identityFunction.functionArn,
      exportName: "BedrockAgentCoreIdentityFunctionArn",
    });

    new cdk.CfnOutput(this, "GatewayFunctionArn", {
      value: gatewayFunction.functionArn,
      exportName: "BedrockAgentCoreGatewayFunctionArn",
    });

    new cdk.CfnOutput(this, "RuntimeFunctionArn", {
      value: runtimeFunction.functionArn,
      exportName: "BedrockAgentCoreRuntimeFunctionArn",
    });

    new cdk.CfnOutput(this, "CredentialsTableName", {
      value: credentialsTable.tableName,
      exportName: "BedrockAgentCoreCredentialsTable",
    });

    new cdk.CfnOutput(this, "OAuthFlowsTableName", {
      value: oauthFlowsTable.tableName,
      exportName: "BedrockAgentCoreOAuthFlowsTable",
    });

    new cdk.CfnOutput(this, "SessionsTableName", {
      value: sessionsTable.tableName,
      exportName: "BedrockAgentCoreSessTable",
    });

    new cdk.CfnOutput(this, "KMSKeyId", {
      value: kmsKey.keyId,
      exportName: "BedrockAgentCoreKMSKeyId",
    });

    new cdk.CfnOutput(this, "GoogleOAuthSecretArn", {
      value: googleOAuthSecret.secretArn,
      exportName: "BedrockAgentCoreGoogleOAuthSecretArn",
    });

    new cdk.CfnOutput(this, "AgentCodeBucketName", {
      value: agentCodeBucket.bucketName,
      exportName: "BedrockAgentCoreCodeBucket",
    });

    new cdk.CfnOutput(this, "LogGroupName", {
      value: logGroup.logGroupName,
      exportName: "BedrockAgentCoreLogGroup",
    });

    console.log(`   ✅ 11 CloudFormation outputs created`);
  }

  private setupTags(): void {
    console.log("🏷️  Applying tags to all stack resources...");

    Tags.of(this).add("Service", "bedrock-agentcore");
    Tags.of(this).add("Platform", "oauth2");
    Tags.of(this).add("Feature", "google-calendar");
    Tags.of(this).add("Architecture", "three-layer");
    Tags.of(this).add("ManagedBy", "CDK");
    Tags.of(this).add("Environment", "development");

    console.log(`   ✅ 6 tags applied to all resources`);
  }
}

// ========== CDK APP ==========
const app = new cdk.App();

new BedrockAgentCoreCompleteStack(app, "BedrockAgentCoreOAuth2V1", {
  env: {
    account: "<AWS_ACCOUNT_ID>",
    region: "eu-central-1",
  },
  description:
    "Complete Bedrock AgentCore OAuth2 Platform with Google Calendar - 100% Infrastructure as Code",
  stackName: "bedrock-agentcore-oauth2-v1-stack",
});

app.synth();
