#!/usr/bin/env node
/**
 * Bedrock AgentCore OAuth2 Platform - CDK App
 * Three-layer OAuth2 with Google Calendar integration
 *
 * Architecture:
 * Client → Identity Service (OAuth2) → Gateway Service (Validation) → Runtime Service (Calendar)
 */

import * as cdk from "aws-cdk-lib";
import {
  aws_lambda as lambda,
  aws_apigatewayv2 as apigw,
  aws_apigatewayv2_integrations as apigw_integrations,
  aws_dynamodb as dynamodb,
  aws_kms as kms,
  aws_iam as iam,
  aws_secretsmanager as secretsmanager,
  Duration,
  RemovalPolicy,
  Tags,
  Stack,
  StackProps,
} from "aws-cdk-lib";
import { Construct } from "constructs";
import * as fs from "fs";
import * as path from "path";

/**
 * Complete Bedrock AgentCore OAuth2 Platform Stack
 */
export class BedrockAgentCoreStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    console.log("\n🚀 BEDROCK AGENTCORE OAUTH2 PLATFORM\n");

    // ========== KMS KEY ==========
    const kmsKey = new kms.Key(this, "KMSKey", {
      enableKeyRotation: true,
      description: "KMS key for Bedrock AgentCore OAuth2",
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

    // ========== SECRETS MANAGER ==========
    const googleOAuthSecret = new secretsmanager.Secret(
      this,
      "GoogleOAuthSecret",
      {
        secretName: "bedrock-agentcore-oauth2/google-oauth",
        description: "Google OAuth2 credentials",
        removalPolicy: RemovalPolicy.RETAIN,
      }
    );

    // ========== IAM ROLE FOR LAMBDA ==========
    const lambdaRole = new iam.Role(this, "LambdaRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      description: "IAM role for Bedrock AgentCore Lambda functions",
      roleName: "bedrock-agentcore-lambda-role",
    });

    credentialsTable.grantReadWriteData(lambdaRole);
    oauthFlowsTable.grantReadWriteData(lambdaRole);
    kmsKey.grantEncryptDecrypt(lambdaRole);
    googleOAuthSecret.grantRead(lambdaRole);

    // ========== READ LAMBDA CODE ==========
    const readLambdaCode = (filename: string): string => {
      const filepath = path.join(__dirname, `../src/deployment/lambdas/${filename}`);
      if (fs.existsSync(filepath)) {
        return fs.readFileSync(filepath, "utf-8");
      }
      return 'exports.handler = async () => ({ statusCode: 500, body: "Handler not found" });';
    };

    // ========== LAMBDA FUNCTIONS ==========
    // Identity Service - OAuth2 Layer 1
    const identityFunction = new lambda.Function(this, "IdentityHandler", {
      functionName: "bedrock-agentcore-identity-handler",
      runtime: lambda.Runtime.PYTHON_3_11,
      code: lambda.Code.fromInline(readLambdaCode("identity_handler.py")),
      handler: "index.handler",
      role: lambdaRole,
      environment: {
        CREDENTIALS_TABLE: credentialsTable.tableName,
        OAUTH_FLOWS_TABLE: oauthFlowsTable.tableName,
        KMS_KEY_ID: kmsKey.keyId,
        GOOGLE_SECRET_ARN: googleOAuthSecret.secretArn,
        REGION: this.region,
      },
      timeout: Duration.seconds(60),
      memorySize: 512,
    });

    // Gateway Service - Authorization Layer 2
    const gatewayFunction = new lambda.Function(this, "GatewayHandler", {
      functionName: "bedrock-agentcore-gateway-handler",
      runtime: lambda.Runtime.PYTHON_3_11,
      code: lambda.Code.fromInline(readLambdaCode("gateway_handler.py")),
      handler: "index.handler",
      role: lambdaRole,
      environment: {
        CREDENTIALS_TABLE: credentialsTable.tableName,
        OAUTH_FLOWS_TABLE: oauthFlowsTable.tableName,
        KMS_KEY_ID: kmsKey.keyId,
        GOOGLE_SECRET_ARN: googleOAuthSecret.secretArn,
        REGION: this.region,
      },
      timeout: Duration.seconds(60),
      memorySize: 512,
    });

    // Runtime Service - Execution Layer 3
    const runtimeFunction = new lambda.Function(this, "RuntimeHandler", {
      functionName: "bedrock-agentcore-runtime-handler",
      runtime: lambda.Runtime.PYTHON_3_11,
      code: lambda.Code.fromInline(readLambdaCode("runtime_handler.py")),
      handler: "index.handler",
      role: lambdaRole,
      environment: {
        CREDENTIALS_TABLE: credentialsTable.tableName,
        OAUTH_FLOWS_TABLE: oauthFlowsTable.tableName,
        KMS_KEY_ID: kmsKey.keyId,
        GOOGLE_SECRET_ARN: googleOAuthSecret.secretArn,
        REGION: this.region,
      },
      timeout: Duration.seconds(60),
      memorySize: 512,
    });

    // ========== API GATEWAY ==========
    const api = new apigw.HttpApi(this, "API", {
      apiName: "bedrock-agentcore-api",
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
      },
    });

    // Integrations
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

    // Routes - Identity Service
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

    // Routes - Gateway Service
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

    // Routes - Runtime Service
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

    // ========== OUTPUTS ==========
    new cdk.CfnOutput(this, "APIEndpoint", {
      value: api.url!,
      description: "API Gateway endpoint",
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

    new cdk.CfnOutput(this, "KMSKeyId", {
      value: kmsKey.keyId,
      exportName: "BedrockAgentCoreKMSKeyId",
    });

    new cdk.CfnOutput(this, "GoogleOAuthSecretArn", {
      value: googleOAuthSecret.secretArn,
      exportName: "BedrockAgentCoreGoogleOAuthSecretArn",
    });

    // ========== TAGS ==========
    Tags.of(this).add("Service", "bedrock-agentcore");
    Tags.of(this).add("Platform", "oauth2");
    Tags.of(this).add("Feature", "google-calendar");
  }
}

// ========== APP ==========
const app = new cdk.App();

new BedrockAgentCoreStack(app, "BedrockAgentCoreStack", {
  env: {
    account: "<AWS_ACCOUNT_ID>",
    region: "eu-central-1",
  },
  description:
    "Bedrock AgentCore OAuth2 Platform with Google Calendar integration",
});

app.synth();
