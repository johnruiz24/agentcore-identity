#!/usr/bin/env node
"use strict";
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
var __extends = (this && this.__extends) || (function () {
    var extendStatics = function (d, b) {
        extendStatics = Object.setPrototypeOf ||
            ({ __proto__: [] } instanceof Array && function (d, b) { d.__proto__ = b; }) ||
            function (d, b) { for (var p in b) if (Object.prototype.hasOwnProperty.call(b, p)) d[p] = b[p]; };
        return extendStatics(d, b);
    };
    return function (d, b) {
        if (typeof b !== "function" && b !== null)
            throw new TypeError("Class extends value " + String(b) + " is not a constructor or null");
        extendStatics(d, b);
        function __() { this.constructor = d; }
        d.prototype = b === null ? Object.create(b) : (__.prototype = b.prototype, new __());
    };
})();
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.BedrockAgentCoreOAuth2Stack = void 0;
var cdk = __importStar(require("aws-cdk-lib"));
var aws_cdk_lib_1 = require("aws-cdk-lib");
var aws_cdk_lib_2 = require("aws-cdk-lib");
// Import REAL Bedrock AgentCore constructs
var aws_bedrock_agentcore_alpha_1 = require("@aws-cdk/aws-bedrock-agentcore-alpha");
var BedrockAgentCoreOAuth2Stack = /** @class */ (function (_super) {
    __extends(BedrockAgentCoreOAuth2Stack, _super);
    function BedrockAgentCoreOAuth2Stack(scope, id, props) {
        var _this = _super.call(this, scope, id, props) || this;
        var accountId = _this.account;
        var region = _this.region;
        console.log("\uD83D\uDE80 Deploying Bedrock AgentCore OAuth2 Platform");
        console.log("   Account: ".concat(accountId));
        console.log("   Region: ".concat(region));
        // ========== KMS KEY ==========
        var kmsKey = new aws_cdk_lib_2.aws_kms.Key(_this, "BedrockAgentCoreKMS", {
            enableKeyRotation: true,
            description: "KMS key for Bedrock AgentCore OAuth2 encryption",
            removalPolicy: aws_cdk_lib_1.RemovalPolicy.RETAIN,
        });
        kmsKey.addAlias("alias/bedrock-agentcore-oauth2");
        // ========== DYNAMODB TABLES ==========
        var credentialsTable = new aws_cdk_lib_2.aws_dynamodb.Table(_this, "CredentialsTable", {
            tableName: "bedrock-agentcore-oauth2-credentials",
            partitionKey: {
                name: "user_id",
                type: aws_cdk_lib_2.aws_dynamodb.AttributeType.STRING,
            },
            sortKey: {
                name: "credential_id",
                type: aws_cdk_lib_2.aws_dynamodb.AttributeType.STRING,
            },
            billingMode: aws_cdk_lib_2.aws_dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption: aws_cdk_lib_2.aws_dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryptionKey: kmsKey,
            removalPolicy: aws_cdk_lib_1.RemovalPolicy.RETAIN,
        });
        var oauthFlowsTable = new aws_cdk_lib_2.aws_dynamodb.Table(_this, "OAuthFlowsTable", {
            tableName: "bedrock-agentcore-oauth2-oauth-flows",
            partitionKey: {
                name: "flow_id",
                type: aws_cdk_lib_2.aws_dynamodb.AttributeType.STRING,
            },
            billingMode: aws_cdk_lib_2.aws_dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption: aws_cdk_lib_2.aws_dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryptionKey: kmsKey,
            removalPolicy: aws_cdk_lib_1.RemovalPolicy.RETAIN,
            timeToLiveAttribute: "ttl",
        });
        var sessionsTable = new aws_cdk_lib_2.aws_dynamodb.Table(_this, "SessionsTable", {
            tableName: "bedrock-agentcore-sessions",
            partitionKey: {
                name: "session_id",
                type: aws_cdk_lib_2.aws_dynamodb.AttributeType.STRING,
            },
            billingMode: aws_cdk_lib_2.aws_dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption: aws_cdk_lib_2.aws_dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryptionKey: kmsKey,
            removalPolicy: aws_cdk_lib_1.RemovalPolicy.RETAIN,
            timeToLiveAttribute: "ttl",
        });
        // ========== GOOGLE OAUTH SECRET ==========
        var googleOAuthSecret = new aws_cdk_lib_2.aws_secretsmanager.Secret(_this, "GoogleOAuthSecret", {
            secretName: "bedrock-agentcore-oauth2/google-oauth",
            description: "Google OAuth2 credentials for Bedrock AgentCore",
            removalPolicy: aws_cdk_lib_1.RemovalPolicy.RETAIN,
        });
        // ========== IAM ROLE FOR BEDROCK AGENTCORE ==========
        var agentcoreRole = new aws_cdk_lib_2.aws_iam.Role(_this, "BedrockAgentCoreRole", {
            assumedBy: new aws_cdk_lib_2.aws_iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
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
        var runtime = new aws_bedrock_agentcore_alpha_1.Runtime(_this, "BedrockRuntime", {
            runtimeName: "bedrock-agentcore-oauth2-runtime",
            executionRole: agentcoreRole,
            artifact: new aws_bedrock_agentcore_alpha_1.AgentRuntimeArtifact(_this, "RuntimeArtifact", {
                s3Location: {
                    bucket: "bedrock-agentcore-artifacts",
                    key: "runtime-handler.zip",
                },
            }),
            networkConfiguration: new aws_bedrock_agentcore_alpha_1.RuntimeNetworkConfiguration(_this, "RuntimeNetwork", {
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
        new cdk.CfnOutput(_this, "RuntimeId", {
            value: runtime.runtimeId,
            description: "Bedrock AgentCore Runtime ID",
            exportName: "BedrockAgentCoreRuntimeId",
        });
        // ========== BEDROCK AGENTCORE GATEWAY ==========
        console.log("🔐 Creating Bedrock AgentCore Gateway...");
        var gateway = new aws_bedrock_agentcore_alpha_1.Gateway(_this, "BedrockGateway", {
            gatewayName: "bedrock-agentcore-oauth2-gateway",
            executionRole: agentcoreRole,
            protocol: new aws_bedrock_agentcore_alpha_1.GatewayProtocolType(aws_bedrock_agentcore_alpha_1.ProtocolType.REST),
            encryptionKey: kmsKey,
        });
        new cdk.CfnOutput(_this, "GatewayId", {
            value: gateway.gatewayId,
            description: "Bedrock AgentCore Gateway ID",
            exportName: "BedrockAgentCoreGatewayId",
        });
        // ========== BEDROCK AGENTCORE MEMORY ==========
        console.log("💾 Creating Bedrock AgentCore Memory...");
        var memory = new aws_bedrock_agentcore_alpha_1.Memory(_this, "BedrockMemory", {
            memoryName: "bedrock-agentcore-session-memory",
            executionRole: agentcoreRole,
            encryptionKey: kmsKey,
            memoryStrategy: new aws_bedrock_agentcore_alpha_1.ManagedMemoryStrategy(),
            eventExpiryDuration: aws_cdk_lib_1.Duration.days(30),
        });
        new cdk.CfnOutput(_this, "MemoryId", {
            value: memory.memoryId,
            description: "Bedrock AgentCore Memory ID",
            exportName: "BedrockAgentCoreMemoryId",
        });
        // ========== OUTPUTS ==========
        new cdk.CfnOutput(_this, "KMSKeyId", {
            value: kmsKey.keyId,
            exportName: "BedrockAgentCoreKMSKeyId",
        });
        new cdk.CfnOutput(_this, "CredentialsTableName", {
            value: credentialsTable.tableName,
            exportName: "BedrockAgentCoreCredentialsTable",
        });
        new cdk.CfnOutput(_this, "OAuthFlowsTableName", {
            value: oauthFlowsTable.tableName,
            exportName: "BedrockAgentCoreOAuthFlowsTable",
        });
        new cdk.CfnOutput(_this, "SessionsTableName", {
            value: sessionsTable.tableName,
            exportName: "BedrockAgentCoreSessionsTable",
        });
        new cdk.CfnOutput(_this, "GoogleOAuthSecretArn", {
            value: googleOAuthSecret.secretArn,
            exportName: "BedrockAgentCoreGoogleOAuthSecretArn",
        });
        new cdk.CfnOutput(_this, "RoleArn", {
            value: agentcoreRole.roleArn,
            exportName: "BedrockAgentCoreRoleArn",
        });
        // ========== TAGS ==========
        aws_cdk_lib_1.Tags.of(_this).add("Service", "bedrock-agentcore");
        aws_cdk_lib_1.Tags.of(_this).add("Platform", "oauth2");
        aws_cdk_lib_1.Tags.of(_this).add("Feature", "google-calendar");
        aws_cdk_lib_1.Tags.of(_this).add("Environment", "production");
        console.log("✅ Bedrock AgentCore OAuth2 Platform stack created");
        return _this;
    }
    return BedrockAgentCoreOAuth2Stack;
}(cdk.Stack));
exports.BedrockAgentCoreOAuth2Stack = BedrockAgentCoreOAuth2Stack;
// ========== APP ==========
var app = new cdk.App();
new BedrockAgentCoreOAuth2Stack(app, "BedrockAgentCoreOAuth2Stack", {
    env: {
        account: "<AWS_ACCOUNT_ID>",
        region: "eu-central-1",
    },
    description: "AWS Bedrock AgentCore OAuth2 Platform with Google Calendar integration",
});
app.synth();
