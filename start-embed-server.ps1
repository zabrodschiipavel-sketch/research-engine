# Локальный эмбеддинг-сервер для research-engine (Фаза 2 ROADMAP).
# nomic-embed-text-v1.5, мультиязычная, 768 измерений — уже была
# скачана локально для LM Studio, отдельно ставить не нужно.
#
# batch-size/ubatch-size подняты до 4096: дефолт 512 токенов слишком
# мал для чанков ~1.5-2.5к символов (см. ROADMAP, Фаза 2 — сервер
# сначала падал с "input too large to process").

$bin = "C:\Users\pavel\llama-turboquant\build\bin\llama-server.exe"
$model = "C:\Users\pavel\.lmstudio\.internal\bundled-models\nomic-ai\nomic-embed-text-v1.5-GGUF\nomic-embed-text-v1.5.Q4_K_M.gguf"

Start-Process -WindowStyle Minimized $bin -ArgumentList @(
  "--embedding",
  "-m", $model,
  "--host", "127.0.0.1", "--port", "8099",
  "--pooling", "mean",
  "-c", "4096", "--batch-size", "4096", "--ubatch-size", "4096"
)

Write-Host "Embedding server starting on :8099 (nomic-embed-text-v1.5)"
Write-Host "Health check: curl http://127.0.0.1:8099/health"
