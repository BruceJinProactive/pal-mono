import type { Plugin } from "@opencode-ai/plugin"
import { appendFileSync, mkdirSync } from "fs"
import { join, dirname } from "path"
import { homedir } from "os"

/**
 * OpenCode tracking plugin — mirrors Claude Code's skill and session tracking.
 *
 * Writes to the same log files as Claude Code hooks for unified analysis:
 * - .claude/skill-usage.log  — skill/command invocations (TSV)
 * - .claude/session-usage.log — per-session cumulative token usage (TSV)
 *
 * Log formats match Claude's hooks exactly so both tools produce interleaved,
 * parseable data in the same files.
 *
 * Auto-loaded by OpenCode from .opencode/plugins/ — no config changes needed.
 */

const messageTokens = new Map<
  string,
  {
    sessionID: string
    model: string
    input: number
    output: number
    cacheRead: number
    cacheWrite: number
    cost: number
  }
>()

const lastWritten = new Map<string, string>()
const pendingWrites = new Map<string, ReturnType<typeof setTimeout>>()

const WRITE_DELAY_MS = 5_000

function appendLog(file: string, line: string): void {
  mkdirSync(dirname(file), { recursive: true })
  appendFileSync(file, line + "\n")
}

function unixTimestamp(): number {
  return Math.floor(Date.now() / 1000)
}

function getSessionTotals(sessionID: string) {
  const totals = {
    model: "unknown",
    input: 0,
    output: 0,
    cacheRead: 0,
    cacheWrite: 0,
    msgCount: 0,
  }

  for (const data of messageTokens.values()) {
    if (data.sessionID === sessionID) {
      totals.input += data.input
      totals.output += data.output
      totals.cacheRead += data.cacheRead
      totals.cacheWrite += data.cacheWrite
      totals.msgCount++
      totals.model = data.model
    }
  }

  return totals
}

const TrackingPlugin: Plugin = async ({ directory }) => {
  const logDir = join(directory, ".claude")
  const skillLogPath = join(logDir, "skill-usage.log")
  const sessionLogPath = join(logDir, "session-usage.log")
  const user =
    process.env.USER || process.env.USERNAME || homedir().split(/[/\\]/).pop() || "unknown"

  function writeSessionUsage(sessionID: string): void {
    const totals = getSessionTotals(sessionID)
    if (totals.msgCount === 0) return

    const fingerprint = `${totals.msgCount}:${totals.input}:${totals.output}:${totals.cacheRead}:${totals.cacheWrite}`
    if (lastWritten.get(sessionID) === fingerprint) return
    lastWritten.set(sessionID, fingerprint)

    // TSV: timestamp  user  session_id  model  input  output  cache_read  cache_write  msg_count
    appendLog(
      sessionLogPath,
      [
        unixTimestamp(),
        user,
        sessionID,
        totals.model,
        totals.input,
        totals.output,
        totals.cacheRead,
        totals.cacheWrite,
        totals.msgCount,
      ].join("\t"),
    )
  }

  function scheduleWrite(sessionID: string): void {
    const existing = pendingWrites.get(sessionID)
    if (existing) clearTimeout(existing)
    pendingWrites.set(
      sessionID,
      setTimeout(() => {
        writeSessionUsage(sessionID)
        pendingWrites.delete(sessionID)
      }, WRITE_DELAY_MS),
    )
  }

  return {
    "command.execute.before": async (input, _output) => {
      // TSV: timestamp  user  session_id  command  (slash-command)
      appendLog(
        skillLogPath,
        [
          unixTimestamp(),
          user,
          input.sessionID,
          input.command,
          "(slash-command)",
        ].join("\t"),
      )
    },

    "tool.execute.after": async (input, _output) => {
      if (input.tool !== "skill") return

      const skillName =
        (input.args as Record<string, unknown>)?.name || "unknown"
      // TSV: timestamp  user  session_id  skill
      appendLog(
        skillLogPath,
        [unixTimestamp(), user, input.sessionID, skillName].join("\t"),
      )
    },

    event: async ({ event }) => {
      try {
        if (event.type === "message.updated") {
          const msg = (event as { properties?: { info?: Record<string, any> } })
            ?.properties?.info
          if (msg?.role === "assistant" && msg.tokens) {
            const tokens = msg.tokens
            messageTokens.set(msg.id, {
              sessionID: msg.sessionID,
              model: msg.modelID || "unknown",
              input: tokens.input ?? 0,
              output: tokens.output ?? 0,
              cacheRead: tokens.cache?.read ?? 0,
              cacheWrite: tokens.cache?.write ?? 0,
              cost: msg.cost ?? 0,
            })
            scheduleWrite(msg.sessionID)
          }
        }

        if (event.type === "session.idle") {
          const sid = (
            event as { properties?: { sessionID?: string } }
          )?.properties?.sessionID
          if (!sid) return
          const pending = pendingWrites.get(sid)
          if (pending) {
            clearTimeout(pending)
            pendingWrites.delete(sid)
          }
          writeSessionUsage(sid)
          // Clean up session data to prevent memory accumulation
          for (const [msgId, data] of messageTokens) {
            if (data.sessionID === sid) messageTokens.delete(msgId)
          }
          lastWritten.delete(sid)
        }
      } catch (err) {
        // Surface errors instead of swallowing — write to debug log
        try {
          appendLog(
            join(logDir, "tracking-debug.log"),
            `[${new Date().toISOString()}] event handler error: ${err}\n  event.type=${(event as any)?.type}`,
          )
        } catch {
          // last-resort: ignore logging failures
        }
      }
    },
  }
}

export default TrackingPlugin
