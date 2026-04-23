#!/usr/bin/env node
/**
 * Bedrock AgentCore OAuth2 + Google Calendar - CDK Stack
 * Simple, direct deployment without confusion
 */

import * as cdk from "aws-cdk-lib";
import { RemovalPolicy, Tags } from "aws-cdk-lib";
import {
  aws_kms as kms,
  aws_iam as iam,
  aws_dynamodb as dynamodb,
  aws_secretsmanager as secrets,
} from "aws-cdk-lib";
import { Construct } from "constructs";

export class BedrockAgentCoreOAuth2Stack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // KMS Key
    const kmsKey = new kms.Key(this, "KMS", {
      enableKeyRotation: true,
      removalPolicy: RemovalPolicy.RETAIN,
    });
    kmsKey.addAlias("alias/bedrock-agentcore-oauth2");

    // DynamoDB - OAuth2 Credentials (encrypted tokens)
    new dynamodb.Table(this, "CredentialsTable", {
      tableName: "bedrock-agentcore-oauth2-credentials",
      partitionKey: { name: "user_id", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "credential_id", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kmsKey,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    // DynamoDB - OAuth2 State (PKCE, state parameter)
    new dynamodb.Table(this, "OAuthFlowsTable", {
      tableName: "bedrock-agentcore-oauth2-oauth-flows",
      partitionKey: { name: "flow_id", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kmsKey,
      removalPolicy: RemovalPolicy.RETAIN,
      timeToLiveAttribute: "ttl",
    });

    // DynamoDB - Sessions
    new dynamodb.Table(this, "SessionsTable", {
      tableName: "bedrock-agentcore-sessions",
      partitionKey: { name: "session_id", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kmsKey,
      removalPolicy: RemovalPolicy.RETAIN,
      timeToLiveAttribute: "ttl",
    });

    // Secrets Manager - Google OAuth
    const googleSecret = new secrets.Secret(this, "GoogleOAuth", {
      secretName: "bedrock-agentcore-oauth2/google-oauth",
      removalPolicy: RemovalPolicy.RETAIN,
    });

    // IAM Role for Bedrock AgentCore
    const agentcoreRole = new iam.Role(this, "BedrockAgentCoreRole", {
      assumedBy: new iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
      roleName: "bedrock-agentcore-oauth2-role",
    });

    // Grant permissions
    agentcoreRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan",
        ],
        resources: [
          `arn:aws:dynamodb:${this.region}:${this.account}:table/bedrock-agentcore-oauth2-credentials`,
          `arn:aws:dynamodb:${this.region}:${this.account}:table/bedrock-agentcore-oauth2-oauth-flows`,
          `arn:aws:dynamodb:${this.region}:${this.account}:table/bedrock-agentcore-sessions`,
        ],
      })
    );

    agentcoreRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"],
        resources: [kmsKey.keyArn],
      })
    );

    agentcoreRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ["secretsmanager:GetSecretValue"],
        resources: [googleSecret.secretArn],
      })
    );

    // Outputs
    new cdk.CfnOutput(this, "KMSKeyId", {
      value: kmsKey.keyId,
      exportName: "BedrockAgentCoreKMSKeyId",
    });

    new cdk.CfnOutput(this, "GoogleOAuthSecretArn", {
      value: googleSecret.secretArn,
      exportName: "BedrockAgentCoreGoogleOAuthSecretArn",
    });

    new cdk.CfnOutput(this, "AgentCoreRoleArn", {
      value: agentcoreRole.roleArn,
      exportName: "BedrockAgentCoreRoleArn",
    });

    Tags.of(this).add("Service", "bedrock-agentcore");
    Tags.of(this).add("Feature", "oauth2-google-calendar");
  }
}

const app = new cdk.App();
new BedrockAgentCoreOAuth2Stack(app, "BedrockAgentCoreOAuth2Stack", {
  env: {
    account: "<AWS_ACCOUNT_ID>",
    region: "eu-central-1",
  },
});
app.synth();
