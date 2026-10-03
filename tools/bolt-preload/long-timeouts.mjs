// Preloaded into Bolt's Node process: let slow local-model calls run up to 30 minutes instead of
// Node's default 300 s headers/body timeouts (non-streaming summary calls were cut at 5 min).
import { Agent, setGlobalDispatcher } from 'undici';
const ms = Number(process.env.WEBGEN_BOLT_FETCH_TIMEOUT_MS || 1800000);
setGlobalDispatcher(new Agent({ headersTimeout: ms, bodyTimeout: ms }));
console.log(`[webgen] fetch headers/body timeout = ${ms} ms`);
