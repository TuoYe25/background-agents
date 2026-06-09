/**
 * Local sandbox provider implementation.
 *
 * Enables sandboxes to run on local machines (e.g., Mac Mini) instead of cloud providers like Modal.
 * This is useful for:
 * - Full closed-loop build/run/test/screenshot/eval from local repos
 * - Lower latency for local development
 * - Working with private repos that can't be accessed from the cloud
 * - Running Electron.js and other local-first applications
 *
 * The local provider communicates with a local sandbox manager via HTTP/WebSocket.
 */

import { createLogger } from "../../../logger";
import type { CorrelationContext } from "../../../logger";
import {
  DEFAULT_SANDBOX_TIMEOUT_SECONDS,
  SandboxProviderError,
  type CreateSandboxConfig,
  type CreateSandboxResult,
  type RestoreConfig,
  type RestoreResult,
  type SandboxProvider,
  type SandboxProviderCapabilities,
  type SnapshotConfig,
  type SnapshotResult,
  type StopConfig,
  type StopResult,
} from "../../provider";

const log = createLogger("local-provider");

export interface LocalProviderConfig {
  /** URL of the local sandbox manager API */
  managerUrl: string;
  /** API key for authenticating with the local manager */
  apiKey: string;
  /** Maximum number of concurrent sandboxes allowed on this local machine */
  maxConcurrentSandboxes?: number;
  /** Whether to enable code-server in local sandboxes */
  codeServerEnabled?: boolean;
}

export interface LocalSandboxInfo {
  sandboxId: string;
  providerObjectId: string;
  status: string;
  createdAt: number;
  codeServerUrl?: string;
  codeServerPassword?: string;
  ttydUrl?: string;
  tunnelUrls?: Record<string, string>;
}

export interface LocalSandboxClient {
  createSandbox(config: CreateSandboxConfig): Promise<LocalSandboxInfo>;
  restoreSandbox(config: RestoreConfig): Promise<{ success: boolean; sandbox?: LocalSandboxInfo; error?: string }>;
  snapshotSandbox(providerObjectId: string, sessionId: string, reason: string): Promise<{ success: boolean; imageId?: string; error?: string }>;
  stopSandbox(providerObjectId: string, sessionId: string): Promise<{ success: boolean; error?: string }>;
  getSandboxStatus(providerObjectId: string): Promise<{ status: string; error?: string }>;
}

export class LocalSandboxProvider implements SandboxProvider {
  readonly name = "local";

  readonly capabilities: SandboxProviderCapabilities = {
    supportsSnapshots: true,
    supportsRestore: true,
    supportsWarm: false,
    supportsPersistentResume: true,
    supportsExplicitStop: true,
  };

  constructor(
    private readonly client: LocalSandboxClient,
    private readonly providerConfig: LocalProviderConfig
  ) {}

  async createSandbox(config: CreateSandboxConfig): Promise<CreateSandboxResult> {
    try {
      log.info("local.create_sandbox", {
        session_id: config.sessionId,
        sandbox_id: config.sandboxId,
        repo_owner: config.repoOwner,
        repo_name: config.repoName,
      });

      const result = await this.client.createSandbox(config);

      log.info("local.sandbox_created", {
        sandbox_id: result.sandboxId,
        provider_object_id: result.providerObjectId,
        status: result.status,
      });

      return {
        sandboxId: result.sandboxId,
        providerObjectId: result.providerObjectId,
        status: result.status,
        createdAt: result.createdAt,
        codeServerUrl: result.codeServerUrl,
        codeServerPassword: result.codeServerPassword,
        ttydUrl: result.ttydUrl,
        tunnelUrls: result.tunnelUrls,
      };
    } catch (error) {
      throw this.classifyError("Failed to create local sandbox", error);
    }
  }

  async restoreFromSnapshot(config: RestoreConfig): Promise<RestoreResult> {
    try {
      log.info("local.restore_sandbox", {
        session_id: config.sessionId,
        snapshot_image_id: config.snapshotImageId,
      });

      const result = await this.client.restoreSandbox(config);

      if (result.success && result.sandbox) {
        return {
          success: true,
          sandboxId: result.sandbox.sandboxId,
          providerObjectId: result.sandbox.providerObjectId,
          codeServerUrl: result.sandbox.codeServerUrl,
          codeServerPassword: result.sandbox.codeServerPassword,
          ttydUrl: result.sandbox.ttydUrl,
          tunnelUrls: result.sandbox.tunnelUrls,
        };
      }

      return {
        success: false,
        error: result.error || "Unknown restore error",
      };
    } catch (error) {
      if (error instanceof SandboxProviderError) throw error;
      throw this.classifyError("Failed to restore local sandbox from snapshot", error);
    }
  }

  async takeSnapshot(config: SnapshotConfig): Promise<SnapshotResult> {
    try {
      log.info("local.take_snapshot", {
        provider_object_id: config.providerObjectId,
        session_id: config.sessionId,
        reason: config.reason,
      });

      const result = await this.client.snapshotSandbox(
        config.providerObjectId,
        config.sessionId,
        config.reason
      );

      if (result.success && result.imageId) {
        return { success: true, imageId: result.imageId };
      }

      return { success: false, error: result.error || "Unknown snapshot error" };
    } catch (error) {
      if (error instanceof SandboxProviderError) throw error;
      throw this.classifyError("Failed to take snapshot of local sandbox", error);
    }
  }

  async stopSandbox(config: StopConfig): Promise<StopResult> {
    try {
      log.info("local.stop_sandbox", {
        provider_object_id: config.providerObjectId,
        session_id: config.sessionId,
        reason: config.reason,
      });

      const result = await this.client.stopSandbox(config.providerObjectId, config.sessionId);

      if (result.success) {
        return { success: true };
      }

      return { success: false, error: result.error || "Unknown stop error" };
    } catch (error) {
      if (error instanceof SandboxProviderError) throw error;
      throw this.classifyError("Failed to stop local sandbox", error);
    }
  }

  private classifyError(message: string, error: unknown): SandboxProviderError {
    if (error instanceof Error) {
      const errorMessage = error.message.toLowerCase();

      if (
        errorMessage.includes("fetch failed") ||
        errorMessage.includes("etimedout") ||
        errorMessage.includes("econnreset") ||
        errorMessage.includes("econnrefused") ||
        errorMessage.includes("network") ||
        errorMessage.includes("timeout") ||
        errorMessage.includes("502") ||
        errorMessage.includes("503") ||
        errorMessage.includes("504") ||
        errorMessage.includes("bad gateway") ||
        errorMessage.includes("service unavailable") ||
        errorMessage.includes("gateway timeout")
      ) {
        return new SandboxProviderError(`${message}: ${error.message}`, "transient", error);
      }
    }

    return new SandboxProviderError(
      `${message}: ${error instanceof Error ? error.message : String(error)}`,
      "permanent",
      error instanceof Error ? error : undefined
    );
  }
}

export function createLocalProvider(
  client: LocalSandboxClient,
  providerConfig: LocalProviderConfig
): LocalSandboxProvider {
  return new LocalSandboxProvider(client, providerConfig);
}