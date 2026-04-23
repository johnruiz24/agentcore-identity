#!/usr/bin/env node
/**
 * AWS Bedrock AgentCore OAuth2 Platform - Real CDK Deployment
 *
 * This stack deploys the REAL AWS BedrockAgentCore service with:
 * - Runtime: Agent execution environment
 * - Gateway: OAuth2 request routing and validation
 * - Memory: Session storage for OAuth2 credentials
 *
 * Usage:
 *   npm install
 *   npx cdk synth
 *   npx cdk deploy
 */

import * as cdk from "aws-cdk-lib";
import { Duration, RemovalPolicy, Tags } from "aws-cdk-lib";
import {
  aws_kms as kms,
  aws_iam as iam,
  aws_dynamodb as dynamodb,
  aws_secretsmanager as secrets,
} from "aws-cdk-lib";
import { Construct } from "constructs";

// Import REAL Bedrock AgentCore constructs
import {
  Runtime,
  Gateway,
  Memory,
  AgentRuntimeArtifact,
  RuntimeNetworkConfiguration,
  ProtocolType,
  GatewayProtocolType,
  ManagedMemoryStrategy,
} from "@aws-cdk/aws-bedrock-agentcore-alpha";

export class BedrockAgentCoreOAuth2Stack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const accountId = this.account;
    const region = this.region;

    console.log(`🚀 Deploying Bedrock AgentCore OAuth2 Platform`);
    console.log(`   Account: ${accountId}`);
    console.log(`   Region: ${region}`);

    // ========== KMS KEY ==========
    const kmsKey = new kms.Key(this, "BedrockAgentCoreKMS", {
      enableKeyRotation: true,
      description: "KMS key for Bedrock AgentCore OAuth2 encryption",
      removalPolicy: RemovalPolicy.RETAIN,
    });

    kmsKey.addAlias("alias/bedrock-agentcore-oauth2");

    // ========== DYNAMODB TABLES ==========
    const credentialsTable = new dynamodb.Table(this, "CredentialsTable", {
      tableName: "bedrock-agentcore-oauth2-credentials",
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
    });

    const oauthFlowsTable = new dynamodb.Table(this, "OAuthFlowsTable", {
      tableName: "bedrock-agentcore-oauth2-oauth-flows",
      partitionKey: {
        name: "flow_id",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kmsKey,
      removalPolicy: RemovalPolicy.RETAIN,
      timeToLiveAttribute: "ttl",
    });

    const sessionsTable = new dynamodb.Table(this, "SessionsTable", {
      tableName: "bedrock-agentcore-sessions",
      partitionKey: {
        name: "session_id",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kmsKey,
      removalPolicy: RemovalPolicy.RETAIN,
      timeToLiveAttribute: "ttl",
    });

    // ========== GOOGLE OAUTH SECRET ==========
    const googleOAuthSecret = new secrets.Secret(this, "GoogleOAuthSecret", {
      secretName: "bedrock-agentcore-oauth2/google-oauth",
      description: "Google OAuth2 credentials for Bedrock AgentCore",
      removalPolicy: RemovalPolicy.RETAIN,
    });

    // ========== IAM ROLE FOR BEDROCK AGENTCORE ==========
    const agentcoreRole = new iam.Role(this, "BedrockAgentCoreRole", {
      assumedBy: new iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
      description: "IAM role for AWS Bedrock AgentCore service",
      roleName: "bedrock-agentcore-service-role",
    });

    // Grant permissions
    credentialsTable.grantReadWriteData(agentcoreRole);
    oauthFlowsTable.grantReadWriteData(agentcoreRole);
    sessionsTable.grantReadWriteData(agentcoreRole);
    kmsKey.grantEncryptDecrypt(agentcoreRole);
    googleOAuthSecret.grantRead(agentcoreRole);

    // ========== BEDROCK AGENTCORE RUNTIME ==========
    console.log("🚀 Creating Bedrock AgentCore Runtime...");

    const runtime = new Runtime(this, "BedrockRuntime", {
      runtimeName: "bedrock-agentcore-oauth2-runtime",
      executionRole: agentcoreRole,
      artifact: new AgentRuntimeArtifact(this, "RuntimeArtifact", {
        s3Location: {
          bucket: "bedrock-agentcore-artifacts",
          key: "runtime-handler.zip",
        },
      }),
      networkConfiguration: new RuntimeNetworkConfiguration(this, "RuntimeNetwork", {
        networkMode: "LAMBDA",
      }),
      environmentVariables: {
        DYNAMODB_TABLE: sessionsTable.tableName,
        CREDENTIALS_TABLE: credentialsTable.tableName,
        OAUTH_FLOWS_TABLE: oauthFlowsTable.tableName,
        KMS_KEY_ID: kmsKey.keyId,
        GOOGLE_SECRET_ARN: googleOAuthSecret.secretArn,
      },
    });

    new cdk.CfnOutput(this, "RuntimeId", {
      value: runtime.runtimeId,
      description: "Bedrock AgentCore Runtime ID",
      exportName: "BedrockAgentCoreRuntimeId",
    });

    // ========== BEDROCK AGENTCORE GATEWAY ==========
    console.log("🔐 Creating Bedrock AgentCore Gateway...");

    const gateway = new Gateway(this, "BedrockGateway", {
      gatewayName: "bedrock-agentcore-oauth2-gateway",
      executionRole: agentcoreRole,
      protocol: new GatewayProtocolType(ProtocolType.REST),
      encryptionKey: kmsKey,
    });

    new cdk.CfnOutput(this, "GatewayId", {
      value: gateway.gatewayId,
      description: "Bedrock AgentCore Gateway ID",
      exportName: "BedrockAgentCoreGatewayId",
    });

    // ========== BEDROCK AGENTCORE MEMORY ==========
    console.log("💾 Creating Bedrock AgentCore Memory...");

    const memory = new Memory(this, "BedrockMemory", {
      memoryName: "bedrock-agentcore-session-memory",
      executionRole: agentcoreRole,
      encryptionKey: kmsKey,
      memoryStrategy: new ManagedMemoryStrategy(),
      eventExpiryDuration: Duration.days(30),
    });

    new cdk.CfnOutput(this, "MemoryId", {
      value: memory.memoryId,
      description: "Bedrock AgentCore Memory ID",
      exportName: "BedrockAgentCoreMemoryId",
    });

    // ========== OUTPUTS ==========
    new cdk.CfnOutput(this, "KMSKeyId", {
      value: kmsKey.keyId,
      exportName: "BedrockAgentCoreKMSKeyId",
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
      exportName: "BedrockAgentCoreSessionsTable",
    });

    new cdk.CfnOutput(this, "GoogleOAuthSecretArn", {
      value: googleOAuthSecret.secretArn,
      exportName: "BedrockAgentCoreGoogleOAuthSecretArn",
    });

    new cdk.CfnOutput(this, "RoleArn", {
      value: agentcoreRole.roleArn,
      exportName: "BedrockAgentCoreRoleArn",
    });

    // ========== TAGS ==========
    Tags.of(this).add("Service", "bedrock-agentcore");
    Tags.of(this).add("Platform", "oauth2");
    Tags.of(this).add("Feature", "google-calendar");
    Tags.of(this).add("Environment", "production");

    console.log("✅ Bedrock AgentCore OAuth2 Platform stack created");
  }
}

// ========== APP ==========
const app = new cdk.App();

new BedrockAgentCoreOAuth2Stack(app, "BedrockAgentCoreOAuth2Stack", {
  env: {
    account: "<AWS_ACCOUNT_ID>",
    region: "eu-central-1",
  },
  description:
    "AWS Bedrock AgentCore OAuth2 Platform with Google Calendar integration",
});

app.synth();
