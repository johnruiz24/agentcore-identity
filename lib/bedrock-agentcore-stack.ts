#!/usr/bin/env node
/**
 * BEDROCK AGENTCORE IDENTITY STACK
 *
 * Baseado em padrões de stack CDK para runtime + gateway + identity.
 */

import * as cdk from "aws-cdk-lib";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as iam from "aws-cdk-lib/aws-iam";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as agentcore from "@aws-cdk/aws-bedrock-agentcore-alpha";
import { Construct } from "constructs";

export interface BedrockAgentCoreStackProps extends cdk.StackProps {
  environment?: string;
  ecrRepositoryName?: string;
  imageTag?: string;
  mcpTargetEnabled?: boolean;
  mcpTargetName?: string;
  mcpTargetDescription?: string;
  mcpTargetEndpoint?: string;
  mcpAuthMode?: "oauth2" | "apiKey" | "iam";
  mcpOauthProviderArn?: string;
  mcpOauthSecretArn?: string;
  mcpOauthScopes?: string[];
  mcpApiKeyProviderArn?: string;
  mcpApiKeySecretArn?: string;
  mcpApiKeyCredentialLocation?: "HEADER" | "QUERY_PARAMETER";
  mcpApiKeyCredentialParameterName?: string;
  googleCalendarTargetEnabled?: boolean;
  googleCalendarTargetName?: string;
  googleCalendarTargetDescription?: string;
  googleCalendarOauthProviderArn?: string;
  googleCalendarOauthSecretArn?: string;
  googleCalendarOauthScopes?: string[];
  atlassianTargetEnabled?: boolean;
  atlassianTargetName?: string;
  atlassianTargetDescription?: string;
  atlassianOauthProviderArn?: string;
  atlassianOauthSecretArn?: string;
  atlassianOauthScopes?: string[];
}

export class BedrockAgentCoreIdentityStack extends cdk.Stack {
  public readonly runtime: agentcore.Runtime;
  public readonly gateway: agentcore.Gateway;
  public readonly memory: agentcore.Memory;
  public readonly mcpTarget?: agentcore.GatewayTarget;
  public readonly googleCalendarTarget?: agentcore.GatewayTarget;
  public readonly atlassianTarget?: agentcore.GatewayTarget;
  public readonly agentArn: string;
  public readonly agentId: string;

  constructor(scope: Construct, id: string, props?: BedrockAgentCoreStackProps) {
    super(scope, id, props);

    const environment = props?.environment || "dev";
    const ecrRepositoryName = props?.ecrRepositoryName || "bedrock-agentcore-identity-oauth2";
    const imageTag = props?.imageTag || "latest";
    const mcpTargetEnabled = props?.mcpTargetEnabled ?? false;
    const mcpTargetName = props?.mcpTargetName || `identity-mcp-${environment}`;
    const mcpTargetDescription = props?.mcpTargetDescription || "External MCP integration target";
    const mcpTargetEndpoint = props?.mcpTargetEndpoint || "";
    const mcpAuthMode = props?.mcpAuthMode || "iam";
    const mcpOauthProviderArn = props?.mcpOauthProviderArn || "";
    const mcpOauthSecretArn = props?.mcpOauthSecretArn || "";
    const mcpOauthScopes = props?.mcpOauthScopes || [];
    const mcpApiKeyProviderArn = props?.mcpApiKeyProviderArn || "";
    const mcpApiKeySecretArn = props?.mcpApiKeySecretArn || "";
    const mcpApiKeyCredentialLocation =
      props?.mcpApiKeyCredentialLocation || "QUERY_PARAMETER";
    const mcpApiKeyCredentialParameterName =
      props?.mcpApiKeyCredentialParameterName || "api_key";
    const googleCalendarTargetEnabled = props?.googleCalendarTargetEnabled ?? false;
    const googleCalendarTargetName =
      props?.googleCalendarTargetName || `google-calendar-openapi-${environment}`;
    const googleCalendarTargetDescription =
      props?.googleCalendarTargetDescription ||
      "Google Calendar OpenAPI target (OAuth user flow)";
    const googleCalendarOauthProviderArn = props?.googleCalendarOauthProviderArn || "";
    const googleCalendarOauthSecretArn = props?.googleCalendarOauthSecretArn || "";
    const googleCalendarOauthScopes = props?.googleCalendarOauthScopes || [
      "https://www.googleapis.com/auth/calendar.events",
    ];
    const atlassianTargetEnabled = props?.atlassianTargetEnabled ?? false;
    const atlassianTargetName =
      props?.atlassianTargetName || `atlassian-openapi-${environment}`;
    const atlassianTargetDescription =
      props?.atlassianTargetDescription ||
      "Atlassian Jira OpenAPI target (OAuth user flow)";
    const atlassianOauthProviderArn = props?.atlassianOauthProviderArn || "";
    const atlassianOauthSecretArn = props?.atlassianOauthSecretArn || "";
    const atlassianOauthScopes = props?.atlassianOauthScopes || [
      "read:jira-work",
      "read:jira-user",
      "offline_access",
    ];

    console.log("\n" + "=".repeat(100));
    console.log("🚀 BEDROCK AGENTCORE IDENTITY - RUNTIME + GATEWAY + MEMORY");
    console.log("=".repeat(100));

    // ========== ECR REPOSITORY ==========
    console.log("\n📌 ECR Repository\n");

    const ecrRepo = ecr.Repository.fromRepositoryName(
      this,
      "IdentityEcrRepo",
      ecrRepositoryName
    );
    console.log(`   ✅ ECR: ${ecrRepositoryName}`);

    // ========== RUNTIME NAME ==========
    console.log("\n📌 Runtime Configuration\n");

    const runtimeName = `bedrock_identity_oauth2_${environment.replace(/-/g, "_")}`;
    console.log(`   ✅ Runtime Name: ${runtimeName}`);

    // ========== BEDROCK AGENTCORE RUNTIME ==========
    console.log("\n📌 Creating Bedrock AgentCore Runtime\n");

    this.runtime = new agentcore.Runtime(this, "IdentityRuntime", {
      runtimeName,
      agentRuntimeArtifact: agentcore.AgentRuntimeArtifact.fromEcrRepository(
        ecrRepo,
        imageTag
      ),
      networkConfiguration: agentcore.RuntimeNetworkConfiguration.usingPublicNetwork(),
      protocolConfiguration: agentcore.ProtocolType.HTTP,
      description: "Bedrock AgentCore Identity Runtime - OAuth2 with Google",
    });

    this.agentArn = this.runtime.agentRuntimeArn;
    this.agentId = this.runtime.agentRuntimeId;

    console.log(`   ✅ Runtime ARN: ${this.agentArn}`);
    console.log(`   ✅ Runtime ID: ${this.agentId}`);

    // ========== GATEWAY AUTH (EXPLICIT COGNITO CONTRACT) ==========
    console.log("\n📌 Creating explicit Cognito authorizer contract\n");

    const userPool = new cognito.UserPool(this, "IdentityGatewayUserPool", {
      userPoolName: `bedrock-agentcore-identity-${environment}-pool`,
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    const readScope: cognito.ResourceServerScope = {
      scopeName: "read",
      scopeDescription: "Read access to gateway tools",
    };
    const writeScope: cognito.ResourceServerScope = {
      scopeName: "write",
      scopeDescription: "Write access to gateway tools",
    };

    const gatewayResourceServer = userPool.addResourceServer(
      "IdentityGatewayResourceServer",
      {
        identifier: `bedrock-agentcore-identity-${environment}`,
        scopes: [readScope, writeScope],
      }
    );

    const gatewayUserPoolClient = userPool.addClient("IdentityGatewayClient", {
      authFlows: {
        userPassword: false,
        userSrp: false,
        adminUserPassword: false,
      },
      generateSecret: true,
      oAuth: {
        flows: {
          clientCredentials: true,
        },
        scopes: [
          cognito.OAuthScope.resourceServer(gatewayResourceServer, readScope),
          cognito.OAuthScope.resourceServer(gatewayResourceServer, writeScope),
        ],
      },
    });

    // Separate user client for USER_FEDERATION flows (human end-user tokens).
    const gatewayUserPoolUserClient = userPool.addClient("IdentityGatewayUserClient", {
      authFlows: {
        userPassword: true,
        userSrp: true,
      },
      generateSecret: false,
      oAuth: {
        flows: {
          authorizationCodeGrant: true,
          implicitCodeGrant: true,
        },
        callbackUrls: ["http://localhost:8765/callback"],
        scopes: [
          cognito.OAuthScope.resourceServer(gatewayResourceServer, readScope),
          cognito.OAuthScope.resourceServer(gatewayResourceServer, writeScope),
        ],
      },
    });

    userPool.addDomain("IdentityGatewayDomain", {
      cognitoDomain: {
        domainPrefix: `bedrockagentcoreidentity${environment.replace(/-/g, "")}gw`,
      },
    });

    const allowedScopes = [
      `${gatewayResourceServer.userPoolResourceServerId}/${readScope.scopeName}`,
      `${gatewayResourceServer.userPoolResourceServerId}/${writeScope.scopeName}`,
    ];

    // ========== GATEWAY ==========
    console.log("\n📌 Creating Bedrock AgentCore Gateway\n");

    this.gateway = new agentcore.Gateway(this, "IdentityGateway", {
      gatewayName: `bedrock-gateway-oauth2-${environment}`,
      description: "Gateway - MCP Protocol with OAuth2",
      authorizerConfiguration: agentcore.GatewayAuthorizer.usingCognito({
        userPool,
        allowedClients: [gatewayUserPoolClient, gatewayUserPoolUserClient],
        allowedScopes,
      }),
    });
    // 3LO OAuth requires MCP 2025-11-25 or later on the gateway.
    const gatewayCfn = this.gateway.node.defaultChild as cdk.CfnResource;
    gatewayCfn.addPropertyOverride("ProtocolConfiguration.Mcp.SupportedVersions", [
      "2025-11-25",
    ]);

    console.log(`   ✅ Gateway created`);

    // Gateway role needs workload token permissions for outbound target auth flows.
    const gatewayServiceRole = this.gateway.node.tryFindChild("ServiceRole") as iam.Role;
    if (gatewayServiceRole) {
      gatewayServiceRole.addToPolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "bedrock-agentcore:GetWorkloadAccessToken",
            "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
            "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
            "bedrock-agentcore:GetResourceOauth2Token",
            "bedrock-agentcore:CompleteResourceTokenAuth",
          ],
          resources: [
            `arn:aws:bedrock-agentcore:${this.region}:${this.account}:token-vault/default`,
            `arn:aws:bedrock-agentcore:${this.region}:${this.account}:workload-identity-directory/default`,
            `arn:aws:bedrock-agentcore:${this.region}:${this.account}:workload-identity-directory/default/workload-identity/*`,
            `arn:aws:bedrock-agentcore:${this.region}:${this.account}:token-vault/default/oauth2credentialprovider/*`,
          ],
        })
      );
      gatewayServiceRole.addToPolicy(
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "bedrock-agentcore:GetResourceOauth2Token",
            "bedrock-agentcore:CompleteResourceTokenAuth",
          ],
          resources: ["*"],
        })
      );
      console.log("   ✅ Gateway workload token IAM permissions configured");
    }

    // ========== MEMORY ==========
    console.log("\n📌 Creating Bedrock AgentCore Memory\n");

    this.memory = new agentcore.Memory(this, "IdentityMemory", {
      memoryName: `bedrock_session_memory_${environment.replace(/-/g, "_")}`,
      description: "Session Memory - Context Storage",
    });

    console.log(`   ✅ Memory created`);

    // ========== OPTIONAL MCP TARGET (OUTBOUND AUTH) ==========
    if (mcpTargetEnabled) {
      if (!mcpTargetEndpoint) {
        throw new Error(
          "mcpTargetEnabled=true requires mcpTargetEndpoint. Set it via CDK context."
        );
      }

      const credentialProviderConfigurations: agentcore.ICredentialProviderConfig[] = [];

      if (mcpAuthMode === "oauth2") {
        if (!mcpOauthProviderArn || !mcpOauthSecretArn || mcpOauthScopes.length === 0) {
          throw new Error(
            "mcpAuthMode=oauth2 requires mcpOauthProviderArn, mcpOauthSecretArn, and at least one mcpOauthScope."
          );
        }
        credentialProviderConfigurations.push(
          agentcore.GatewayCredentialProvider.fromOauthIdentityArn({
            providerArn: mcpOauthProviderArn,
            secretArn: mcpOauthSecretArn,
            scopes: mcpOauthScopes,
          })
        );
      } else if (mcpAuthMode === "apiKey") {
        if (!mcpApiKeyProviderArn || !mcpApiKeySecretArn) {
          throw new Error(
            "mcpAuthMode=apiKey requires mcpApiKeyProviderArn and mcpApiKeySecretArn."
          );
        }
        const credentialLocation =
          mcpApiKeyCredentialLocation === "HEADER"
            ? agentcore.ApiKeyCredentialLocation.header({
                credentialParameterName: mcpApiKeyCredentialParameterName,
              })
            : agentcore.ApiKeyCredentialLocation.queryParameter({
                credentialParameterName: mcpApiKeyCredentialParameterName,
              });
        credentialProviderConfigurations.push(
          agentcore.GatewayCredentialProvider.fromApiKeyIdentityArn({
            providerArn: mcpApiKeyProviderArn,
            secretArn: mcpApiKeySecretArn,
            credentialLocation,
          })
        );
      } else {
        credentialProviderConfigurations.push(
          agentcore.GatewayCredentialProvider.fromIamRole()
        );
      }

      console.log("\n📌 Creating Bedrock AgentCore Gateway MCP Target\n");
      this.mcpTarget = this.gateway.addMcpServerTarget("IdentityMcpTarget", {
        gatewayTargetName: mcpTargetName,
        description: mcpTargetDescription,
        endpoint: mcpTargetEndpoint,
        credentialProviderConfigurations,
      });
      console.log(`   ✅ MCP Target created (${mcpAuthMode})`);
    }

    // ========== OPTIONAL GOOGLE CALENDAR OPENAPI TARGET ==========
    if (googleCalendarTargetEnabled) {
      if (
        !googleCalendarOauthProviderArn ||
        !googleCalendarOauthSecretArn ||
        googleCalendarOauthScopes.length === 0
      ) {
        throw new Error(
          "googleCalendarTargetEnabled=true requires googleCalendarOauthProviderArn, googleCalendarOauthSecretArn, and at least one scope."
        );
      }

      const googleCalendarOpenApiSchema = JSON.stringify(
        {
          openapi: "3.0.3",
          info: {
            title: "Google Calendar API (Subset)",
            version: "v3",
          },
          servers: [
            {
              url: "https://www.googleapis.com/calendar/v3",
            },
          ],
          paths: {
            "/calendars/{calendarId}/events": {
              post: {
                operationId: "createCalendarEvent",
                summary: "Create an event in a Google Calendar",
                parameters: [
                  {
                    name: "calendarId",
                    in: "path",
                    required: true,
                    schema: { type: "string" },
                  },
                ],
                requestBody: {
                  required: true,
                  content: {
                    "application/json": {
                      schema: {
                        type: "object",
                        properties: {
                          summary: { type: "string" },
                          description: { type: "string" },
                          start: {
                            type: "object",
                            properties: {
                              dateTime: { type: "string" },
                              timeZone: { type: "string" },
                            },
                            required: ["dateTime"],
                          },
                          end: {
                            type: "object",
                            properties: {
                              dateTime: { type: "string" },
                              timeZone: { type: "string" },
                            },
                            required: ["dateTime"],
                          },
                        },
                        required: ["summary", "start", "end"],
                      },
                    },
                  },
                },
                responses: {
                  "200": { description: "Event created" },
                  "201": { description: "Event created" },
                },
              },
            },
          },
        },
        null,
        2
      );

      console.log("\n📌 Creating Google Calendar OpenAPI Target\n");
      this.googleCalendarTarget = this.gateway.addOpenApiTarget(
        "GoogleCalendarOpenApiTarget",
        {
          gatewayTargetName: googleCalendarTargetName,
          description: googleCalendarTargetDescription,
          apiSchema: agentcore.ApiSchema.fromInline(googleCalendarOpenApiSchema),
          credentialProviderConfigurations: [
            agentcore.GatewayCredentialProvider.fromOauthIdentityArn({
              providerArn: googleCalendarOauthProviderArn,
              secretArn: googleCalendarOauthSecretArn,
              scopes: googleCalendarOauthScopes,
            }),
          ],
        }
      );
      // Force user-consent OAuth flow for Google Calendar target.
      // The L2 helper does not currently expose grantType/defaultReturnUrl.
      const googleCalendarTargetCfn = this.googleCalendarTarget.node
        .defaultChild as cdk.CfnResource;
      googleCalendarTargetCfn.addPropertyOverride(
        "CredentialProviderConfigurations.0.CredentialProvider.OauthCredentialProvider.GrantType",
        "AUTHORIZATION_CODE"
      );
      googleCalendarTargetCfn.addPropertyOverride(
        "CredentialProviderConfigurations.0.CredentialProvider.OauthCredentialProvider.DefaultReturnUrl",
        "http://localhost:8765/callback"
      );
      console.log("   ✅ Google Calendar OpenAPI target created");
    }

    // ========== OPTIONAL ATLASSIAN JIRA OPENAPI TARGET ==========
    if (atlassianTargetEnabled) {
      if (
        !atlassianOauthProviderArn ||
        !atlassianOauthSecretArn ||
        atlassianOauthScopes.length === 0
      ) {
        throw new Error(
          "atlassianTargetEnabled=true requires atlassianOauthProviderArn, atlassianOauthSecretArn, and at least one scope."
        );
      }

      const atlassianOpenApiSchema = JSON.stringify(
        {
          openapi: "3.0.3",
          info: {
            title: "Atlassian API (Jira Subset)",
            version: "v1",
          },
          servers: [
            {
              url: "https://api.atlassian.com",
            },
          ],
          paths: {
            "/oauth/token/accessible-resources": {
              get: {
                operationId: "listAtlassianAccessibleResources",
                summary: "List Atlassian sites available to the authenticated user",
                responses: {
                  "200": { description: "Accessible resources returned" },
                },
              },
            },
            "/ex/jira/{cloudId}/rest/api/3/project/search": {
              get: {
                operationId: "searchJiraProjects",
                summary: "List Jira projects the user can browse",
                parameters: [
                  {
                    name: "cloudId",
                    in: "path",
                    required: true,
                    schema: { type: "string" },
                  },
                  {
                    name: "query",
                    in: "query",
                    required: false,
                    schema: { type: "string" },
                  },
                  {
                    name: "maxResults",
                    in: "query",
                    required: false,
                    schema: { type: "integer", default: 20 },
                  },
                  {
                    name: "fields",
                    in: "query",
                    required: false,
                    schema: { type: "string" },
                  },
                ],
                responses: {
                  "200": { description: "Projects returned" },
                },
              },
            },
            "/ex/jira/{cloudId}/rest/api/3/search/jql": {
              get: {
                operationId: "searchJiraIssues",
                summary: "Search Jira issues visible to the user",
                parameters: [
                  {
                    name: "cloudId",
                    in: "path",
                    required: true,
                    schema: { type: "string" },
                  },
                  {
                    name: "jql",
                    in: "query",
                    required: true,
                    schema: { type: "string" },
                  },
                  {
                    name: "maxResults",
                    in: "query",
                    required: false,
                    schema: { type: "integer", default: 20 },
                  },
                ],
                responses: {
                  "200": { description: "Issues returned" },
                },
              },
              post: {
                operationId: "searchJiraIssuesDetailed",
                summary: "Search Jira issues with explicit fields payload",
                parameters: [
                  {
                    name: "cloudId",
                    in: "path",
                    required: true,
                    schema: { type: "string" },
                  },
                ],
                requestBody: {
                  required: true,
                  content: {
                    "application/json": {
                      schema: {
                        type: "object",
                        properties: {
                          jql: { type: "string" },
                          maxResults: { type: "integer", default: 20 },
                          fields: {
                            type: "array",
                            items: { type: "string" },
                          },
                        },
                        required: ["jql"],
                      },
                    },
                  },
                },
                responses: {
                  "200": { description: "Detailed issues returned" },
                },
              },
            },
          },
        },
        null,
        2
      );

      console.log("\n📌 Creating Atlassian Jira OpenAPI Target\n");
      this.atlassianTarget = this.gateway.addOpenApiTarget("AtlassianOpenApiTarget", {
        gatewayTargetName: atlassianTargetName,
        description: atlassianTargetDescription,
        apiSchema: agentcore.ApiSchema.fromInline(atlassianOpenApiSchema),
        credentialProviderConfigurations: [
          agentcore.GatewayCredentialProvider.fromOauthIdentityArn({
            providerArn: atlassianOauthProviderArn,
            secretArn: atlassianOauthSecretArn,
            scopes: atlassianOauthScopes,
          }),
        ],
      });
      const atlassianTargetCfn = this.atlassianTarget.node.defaultChild as cdk.CfnResource;
      atlassianTargetCfn.addPropertyOverride(
        "CredentialProviderConfigurations.0.CredentialProvider.OauthCredentialProvider.GrantType",
        "AUTHORIZATION_CODE"
      );
      atlassianTargetCfn.addPropertyOverride(
        "CredentialProviderConfigurations.0.CredentialProvider.OauthCredentialProvider.DefaultReturnUrl",
        "https://example.atlassian.net"
      );
      console.log("   ✅ Atlassian Jira OpenAPI target created");
    }

    // ========== IAM PERMISSIONS ==========
    console.log("\n📌 Configuring IAM Permissions\n");

    // Get the execution role created by Runtime
    const executionRole = this.runtime.node.tryFindChild("ExecutionRole") as iam.Role;

    if (executionRole) {
      // Add Bedrock permissions
      const bedrockPolicy = new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:Converse",
          "bedrock:ConverseStream",
          "bedrock:GetFoundationModel",
          "bedrock:ListFoundationModels",
        ],
        resources: [
          "arn:aws:bedrock:*::foundation-model/*",
          `arn:aws:bedrock:*:${this.account}:inference-profile/*`,
        ],
      });

      // Add Secrets Manager permissions
      const secretsPolicy = new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["secretsmanager:GetSecretValue"],
        resources: [
          `arn:aws:secretsmanager:${this.region}:${this.account}:secret:bedrock-agentcore/*`,
        ],
      });

      // Add DynamoDB permissions
      const dynamoPolicy = new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan",
        ],
        resources: [
          `arn:aws:dynamodb:${this.region}:${this.account}:table/bedrock-agentcore-*`,
        ],
      });

      executionRole.addToPolicy(bedrockPolicy);
      executionRole.addToPolicy(secretsPolicy);
      executionRole.addToPolicy(dynamoPolicy);

      console.log(`   ✅ IAM Permissions configured`);
    }

    // ========== OUTPUTS ==========
    console.log("\n📌 CloudFormation Outputs\n");

    new cdk.CfnOutput(this, "RuntimeArn", {
      value: this.agentArn,
      exportName: `BedrockIdentityRuntimeArn-${environment}`,
      description: "ARN of the Identity Runtime",
    });

    new cdk.CfnOutput(this, "RuntimeId", {
      value: this.agentId,
      exportName: `BedrockIdentityRuntimeId-${environment}`,
      description: "ID of the Identity Runtime",
    });

    new cdk.CfnOutput(this, "GatewayName", {
      value: this.gateway.name,
      exportName: `BedrockGatewayName-${environment}`,
      description: "Name of the Gateway",
    });

    new cdk.CfnOutput(this, "GatewayUserClientId", {
      value: gatewayUserPoolUserClient.userPoolClientId,
      exportName: `BedrockGatewayUserClientId-${environment}`,
      description: "Cognito user client for USER_FEDERATION tests",
    });

    new cdk.CfnOutput(this, "MemoryName", {
      value: this.memory.memoryName,
      exportName: `BedrockMemoryName-${environment}`,
      description: "Name of the Memory storage",
    });

    if (this.mcpTarget) {
      new cdk.CfnOutput(this, "GatewayTargetId", {
        value: this.mcpTarget.targetId,
        exportName: `BedrockGatewayTargetId-${environment}`,
        description: "ID of the configured MCP gateway target",
      });
      new cdk.CfnOutput(this, "GatewayTargetName", {
        value: this.mcpTarget.name,
        exportName: `BedrockGatewayTargetName-${environment}`,
        description: "Name of the configured MCP gateway target",
      });
    }
    if (this.googleCalendarTarget) {
      new cdk.CfnOutput(this, "GoogleCalendarTargetId", {
        value: this.googleCalendarTarget.targetId,
        exportName: `BedrockGoogleCalendarTargetId-${environment}`,
        description: "ID of the Google Calendar OpenAPI target",
      });
      new cdk.CfnOutput(this, "GoogleCalendarTargetName", {
        value: this.googleCalendarTarget.name,
        exportName: `BedrockGoogleCalendarTargetName-${environment}`,
        description: "Name of the Google Calendar OpenAPI target",
      });
    }
    if (this.atlassianTarget) {
      new cdk.CfnOutput(this, "AtlassianTargetId", {
        value: this.atlassianTarget.targetId,
        exportName: `BedrockAtlassianTargetId-${environment}`,
        description: "ID of the Atlassian OpenAPI target",
      });
      new cdk.CfnOutput(this, "AtlassianTargetName", {
        value: this.atlassianTarget.name,
        exportName: `BedrockAtlassianTargetName-${environment}`,
        description: "Name of the Atlassian OpenAPI target",
      });
    }

    console.log(`   ✅ Outputs exported`);

    // ========== TAGS ==========
    cdk.Tags.of(this).add("Service", "bedrock-agentcore-identity");
    cdk.Tags.of(this).add("Component", "runtime-gateway-memory");
    cdk.Tags.of(this).add("Environment", environment);

    console.log("\n" + "=".repeat(100));
    console.log("✅ BEDROCK AGENTCORE IDENTITY STACK COMPLETE");
    console.log("=".repeat(100) + "\n");
  }
}

const app = new cdk.App();
const toBool = (value: unknown): boolean =>
  value === true || value === "true" || value === "1";

const environment = app.node.tryGetContext("environment") || "dev";
const imageTag = app.node.tryGetContext("imageTag") || "latest";
const mcpTargetEnabled = toBool(app.node.tryGetContext("mcpTargetEnabled"));
const mcpTargetName = app.node.tryGetContext("mcpTargetName");
const mcpTargetDescription = app.node.tryGetContext("mcpTargetDescription");
const mcpTargetEndpoint = app.node.tryGetContext("mcpTargetEndpoint");
const mcpAuthMode = app.node.tryGetContext("mcpAuthMode");
const mcpOauthProviderArn = app.node.tryGetContext("mcpOauthProviderArn");
const mcpOauthSecretArn = app.node.tryGetContext("mcpOauthSecretArn");
const mcpOauthScopesRaw = app.node.tryGetContext("mcpOauthScopes");
const mcpApiKeyProviderArn = app.node.tryGetContext("mcpApiKeyProviderArn");
const mcpApiKeySecretArn = app.node.tryGetContext("mcpApiKeySecretArn");
const mcpApiKeyCredentialLocation = app.node.tryGetContext("mcpApiKeyCredentialLocation");
const mcpApiKeyCredentialParameterName = app.node.tryGetContext(
  "mcpApiKeyCredentialParameterName"
);
const googleCalendarTargetEnabled = toBool(
  app.node.tryGetContext("googleCalendarTargetEnabled")
);
const googleCalendarTargetName = app.node.tryGetContext("googleCalendarTargetName");
const googleCalendarTargetDescription = app.node.tryGetContext(
  "googleCalendarTargetDescription"
);
const googleCalendarOauthProviderArn = app.node.tryGetContext(
  "googleCalendarOauthProviderArn"
);
const googleCalendarOauthSecretArn = app.node.tryGetContext(
  "googleCalendarOauthSecretArn"
);
const googleCalendarOauthScopesRaw = app.node.tryGetContext(
  "googleCalendarOauthScopes"
);
const atlassianTargetEnabled = toBool(app.node.tryGetContext("atlassianTargetEnabled"));
const atlassianTargetName = app.node.tryGetContext("atlassianTargetName");
const atlassianTargetDescription = app.node.tryGetContext("atlassianTargetDescription");
const atlassianOauthProviderArn = app.node.tryGetContext("atlassianOauthProviderArn");
const atlassianOauthSecretArn = app.node.tryGetContext("atlassianOauthSecretArn");
const atlassianOauthScopesRaw = app.node.tryGetContext("atlassianOauthScopes");
const mcpOauthScopes =
  typeof mcpOauthScopesRaw === "string"
    ? mcpOauthScopesRaw
        .split(",")
        .map((v: string) => v.trim())
        .filter((v: string) => v.length > 0)
    : Array.isArray(mcpOauthScopesRaw)
      ? mcpOauthScopesRaw
      : [];
const googleCalendarOauthScopes =
  typeof googleCalendarOauthScopesRaw === "string"
    ? googleCalendarOauthScopesRaw
        .split(",")
        .map((v: string) => v.trim())
        .filter((v: string) => v.length > 0)
    : Array.isArray(googleCalendarOauthScopesRaw)
      ? googleCalendarOauthScopesRaw
      : [];
const atlassianOauthScopes =
  typeof atlassianOauthScopesRaw === "string"
    ? atlassianOauthScopesRaw
        .split(",")
        .map((v: string) => v.trim())
        .filter((v: string) => v.length > 0)
    : Array.isArray(atlassianOauthScopesRaw)
      ? atlassianOauthScopesRaw
      : [];
const account = "<AWS_ACCOUNT_ID>";
const region = "eu-central-1";

new BedrockAgentCoreIdentityStack(app, "BedrockIdentityFull", {
  stackName: `bedrock-agentcore-identity-${environment}`,
  description: "Bedrock AgentCore Identity - Runtime + Gateway + Memory",
  environment: environment,
  ecrRepositoryName: "bedrock-agentcore-identity-oauth2",
  imageTag: imageTag,
  mcpTargetEnabled,
  mcpTargetName,
  mcpTargetDescription,
  mcpTargetEndpoint,
  mcpAuthMode,
  mcpOauthProviderArn,
  mcpOauthSecretArn,
  mcpOauthScopes,
  mcpApiKeyProviderArn,
  mcpApiKeySecretArn,
  mcpApiKeyCredentialLocation,
  mcpApiKeyCredentialParameterName,
  googleCalendarTargetEnabled,
  googleCalendarTargetName,
  googleCalendarTargetDescription,
  googleCalendarOauthProviderArn,
  googleCalendarOauthSecretArn,
  googleCalendarOauthScopes,
  atlassianTargetEnabled,
  atlassianTargetName,
  atlassianTargetDescription,
  atlassianOauthProviderArn,
  atlassianOauthSecretArn,
  atlassianOauthScopes,
  env: {
    account,
    region,
  },
});

app.synth();
