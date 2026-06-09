/**
 * HTTP client for communicating with the local sandbox manager.
 * 
 * The local sandbox manager runs on a local machine (e.g., Mac Mini) and manages
 * sandbox lifecycle operations. This client handles the communication between
 * the control plane and the local manager.
 */

import { createLogger } from "../../../logger";
import type { CreateSandboxConfig } from "../../provider";
import type { RestoreConfig } from "../../provider";
import type { LocalSandboxClient, LocalSandboxInfo, LocalProviderConfig } from "./provider";

const log = createLogger("local-client");

interface LocalApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export class LocalSandboxHttpClient implements LocalSandboxClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;

  constructor(config: LocalProviderConfig) {
    this.baseUrl = config.managerUrl.replace(/\/$/, "");
    this.apiKey = config.apiKey;
  }

  private async getHeaders(): Promise<Record<string, string>> {
    return {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${this.apiKey}`,
    };
  }

  async createSandbox(config: CreateSandboxConfig): Promise<LocalSandboxInfo> {
    const startTime = Date.now();
    const endpoint = "create-sandbox";

    try {
      const headers = await this.getHeaders();
      const response = await fetch(`${this.baseUrl}/${endpoint}`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          session_id: config.sessionId,
          sandbox_id: config.sandboxId,
          repo_owner: config.repoOwner,
          repo_name: config.repoName,
          control_plane_url: config.controlPlaneUrl,
          sandbox_auth_token: config.sandboxAuthToken,
          provider: config.provider,
          model: config.model,
          user_env_vars: config.userEnvVars || null,
          repo_image_id: config.repoImageId || null,
          repo_image_sha: config.repoImageSha || null,
          timeout_seconds: config.timeoutSeconds || DEFAULT_SANDBOX_TIMEOUT_SECONDS,
          branch: config.branch || null,
          code_server_enabled: config.codeServerEnabled ?? false,
          agent_slack_notify_enabled: config.agentSlackNotifyEnabled ?? false,
          mcp_servers: config.mcpServers || null,
          sandbox_settings: config.sandboxSettings || null,
        }),
      });

      const result = (await response.json()) as LocalApiResponse<{
        sandbox_id: string;
        provider_object_id: string;
        status: string;
        created_at: number;
        code_server_url?: string;
        code_server_password?: string;
        ttyd_url?: string;
        tunnel_urls?: Record<string, string>;
      }>;

      if (!result.success || !result.data) {
        throw new Error(result.error || "Failed to create sandbox");
      }

      log.info("local.client.create_sandbox", {
        endpoint,
        session_id: config.sessionId,
        sandbox_id: config.sandboxId,
        duration_ms: Date.now() - startTime,
      });

      return {
        sandboxId: result.data.sandbox_id,
        providerObjectId: result.data.provider_object_id,
        status: result.data.status,
        createdAt: result.data.created_at,
        codeServerUrl: result.data.code_server_url,
        codeServerPassword: result.data.code_server_password,
        ttydUrl: result.data.ttyd_url,
        tunnelUrls: result.data.tunnel_urls,
      };
    } catch (error) {
      log.error("local.client.create_sandbox_failed", {
        endpoint,
        session_id: config.sessionId,
        error: error instanceof Error ? error.message : String(error),
        duration_ms: Date.now() - startTime,
      });
      throw error;
    }
  }

  async restoreSandbox(config: RestoreConfig): Promise<{ success: boolean; sandbox?: LocalSandboxInfo; error?: string }> {
    const startTime = Date.now();
    const endpoint = "restore-sandbox";

    try {
      const headers = await this.getHeaders();
      const response = await fetch(`${this.baseUrl}/${endpoint}`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          snapshot_image_id: config.snapshotImageId,
          session_id: config.sessionId,
          sandbox_id: config.sandboxId,
          sandbox_auth_token: config.sandboxAuthToken,
          control_plane_url: config.controlPlaneUrl,
          repo_owner: config.repoOwner,
          repo_name: config.repoName,
          provider: config.provider,
          model: config.model,
          user_env_vars: config.userEnvVars || null,
          timeout_seconds: config.timeoutSeconds || DEFAULT_SANDBOX_TIMEOUT_SECONDS,
          branch: config.branch || null,
          code_server_enabled: config.codeServerEnabled ?? false,
          agent_slack_notify_enabled: config.agentSlackNotifyEnabled ?? false,
          mcp_servers: config.mcpServers || null,
          sandbox_settings: config.sandboxSettings || null,
        }),
      });

      const result = (await response.json()) as LocalApiResponse<{
        sandbox_id: string;
        provider_object_id: string;
        status: string;
        created_at: number;
        code_server_url?: string;
        code_server_password?: string;
        ttyd_url?: string;
        tunnel_urls?: Record<string, string>;
      }>;

      log.info("local.client.restore_sandbox", {
        endpoint,
        session_id: config.sessionId,
        snapshot_image_id: config.snapshotImageId,
        success: result.success,
        duration_ms: Date.now() - startTime,
      });

      if (result.success && result.data) {
        return {
          success: true,
          sandbox: {
            sandboxId: result.data.sandbox_id,
            providerObjectId: result.data.provider_object_id,
            status: result.data.status,
            createdAt: result.data.created_at,
            codeServerUrl: result.data.code_server_url,
            codeServerPassword: result.data.code_server_password,
            ttydUrl: result.data.ttyd_url,
            tunnelUrls: result.data.tunnel_urls,
          },
        };
      }

      return { success: false, error: result.error || "Unknown restore error" };
    } catch (error) {
      log.error("local.client.restore_sandbox_failed", {
        endpoint,
        session_id: config.sessionId,
        snapshot_image_id: config.snapshotImageId,
        error: error instanceof Error ? error.message : String(error),
        duration_ms: Date.now() - startTime,
      });
      throw error;
    }
  }

  async snapshotSandbox(providerObjectId: string, sessionId: string, reason: string): Promise<{ success: boolean; imageId?: string; error?: string }> {
    const startTime = Date.now();
    const endpoint = "snapshot-sandbox";

    try {
      const headers = await this.getHeaders();
      const response = await fetch(`${this.baseUrl}/${endpoint}`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          provider_object_id: providerObjectId,
          session_id: sessionId,
          reason,
        }),
      });

      const result = (await response.json()) as LocalApiResponse<{ image_id: string }>;

      log.info("local.client.snapshot_sandbox", {
        endpoint,
        session_id: sessionId,
        provider_object_id: providerObjectId,
        success: result.success,
        duration_ms: Date.now() - startTime,
      });

      if (result.success && result.data?.image_id) {
        return { success: true, imageId: result.data.image_id };
      }

      return { success: false, error: result.error || "Unknown snapshot error" };
    } catch (error) {
      log.error("local.client.snapshot_sandbox_failed", {
        endpoint,
        session_id: sessionId,
        provider_object_id: providerObjectId,
        error: error instanceof Error ? error.message : String(error),
        duration_ms: Date.now() - startTime,
      });
      throw error;
    }
  }

  async stopSandbox(providerObjectId: string, sessionId: string): Promise<{ success: boolean; error?: string }> {
    const startTime = Date.now();
    const endpoint = "stop-sandbox";

    try {
      const headers = await this.getHeaders();
      const response = await fetch(`${this.baseUrl}/${endpoint}`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          provider_object_id: providerObjectId,
          session_id: sessionId,
        }),
      });

      const result = (await response.json()) as LocalApiResponse<unknown>;

      log.info("local.client.stop_sandbox", {
        endpoint,
        session_id: sessionId,
        provider_object_id: providerObjectId,
        success: result.success,
        duration_ms: Date.now() - startTime,
      });

      if (result.success) {
        return { success: true };
      }

      return { success: false, error: result.error || "Unknown stop error" };
    } catch (error) {
      log.error("local.client.stop_sandbox_failed", {
        endpoint,
        session_id: sessionId,
        provider_object_id: providerObjectId,
        error: error instanceof Error ? error.message : String(error),
        duration_ms: Date.now() - startTime,
      });
      throw error;
    }
  }

  async getSandboxStatus(providerObjectId: string): Promise<{ status: string; error?: string }> {
    const startTime = Date.now();
    const endpoint = "sandbox-status";

    try {
      const headers = await this.getHeaders();
      const response = await fetch(`${this.baseUrl}/${endpoint}/${providerObjectId}`, {
        method: "GET",
        headers,
      });

      const result = (await response.json()) as LocalApiResponse<{ status: string }>;

      log.info("local.client.get_sandbox_status", {
        endpoint,
        provider_object_id: providerObjectId,
        duration_ms: Date.now() - startTime,
      });

      if (result.success && result.data) {
        return { status: result.data.status };
      }

      return { status: "unknown", error: result.error || "Unknown status error" };
    } catch (error) {
      log.error("local.client.get_sandbox_status_failed", {
        endpoint,
        provider_object_id: providerObjectId,
        error: error instanceof Error ? error.message : String(error),
        duration_ms: Date.now() - startTime,
      });
      throw error;
    }
  }
}

/** Default sandbox timeout in seconds (2 hours) */
const DEFAULT_SANDBOX_TIMEOUT_SECONDS = 7200;

export function createLocalSandboxClient(config: LocalProviderConfig): LocalSandboxHttpClient {
  return new LocalSandboxHttpClient(config);
}