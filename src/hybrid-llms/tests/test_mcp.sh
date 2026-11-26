#!/bin/sh
# test_mcp.sh - drive `hybrid-llms mcp` over stdio and check the JSON-RPC replies.
# Usage: sh tests/test_mcp.sh ./build/hybrid-llms
set -eu
BIN=${1:-./build/hybrid-llms}
TMP=$(mktemp -d "${TMPDIR:-/tmp}/hybrid-mcp-XXXXXX")
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/models"
: > "$TMP/models/tiny-test.gguf"

OUT="$TMP/out.jsonl"
{
  echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}'
  echo '{"jsonrpc":"2.0","method":"notifications/initialized"}'
  echo '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
  echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"local_models","arguments":{}}}'
  echo '{"jsonrpc":"2.0","id":4,"method":"prompts/get","params":{"name":"hybrid","arguments":{"request":"hi"}}}'
  echo '{"jsonrpc":"2.0","id":5,"method":"nope"}'
  echo 'not json'
  echo '{"jsonrpc":"2.0","id":"s6","method":"ping"}'
} | HYBRID_LLMS_CONFIG=/dev/null HYBRID_LLMS_MODELS_DIR="$TMP/models" "$BIN" -q mcp > "$OUT"

fail=0
expect() {
  if grep -q -- "$1" "$OUT"; then :; else echo "FAIL: expected $1" >&2; fail=1; fi
}
expect '"id":1,"result":{"protocolVersion":"2025-06-18"'
expect '"name":"hybrid"'
expect '"name":"local_generate"'
expect '"name":"cloud_ask"'
expect 'tiny-test.gguf'
expect '"id":4,"result"'
expect '"id":5,"error":{"code":-32601'
expect '"code":-32700'
expect '"id":"s6","result":{}'
lines=$(wc -l < "$OUT" | tr -d ' ')
[ "$lines" = 7 ] || { echo "FAIL: expected 7 replies, got $lines" >&2; fail=1; }
[ $fail = 0 ] && echo "mcp: ok"
exit $fail
