import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/browser',
  use: { baseURL: 'http://127.0.0.1:5173', channel: 'msedge' },
  webServer: [
    {
      command: 'python tests/browser/mock_model.py',
      url: 'http://127.0.0.1:8101',
      reuseExistingServer: false,
    },
    {
      command: 'npm run dev',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: false,
    },
    {
      command: 'python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000',
      url: 'http://127.0.0.1:8000/api/examples/quadratic',
      env: { QUIZ_DB_PATH: process.env.BROWSER_QUIZ_DB_PATH ?? '.local/browser-quiz.sqlite3', MODEL_BASE_URL: 'http://127.0.0.1:8101',
        MODEL_API_KEY: 'browser-test', MODEL_NAME: 'browser-test', EXAM_DEEPSEEK_API_KEY: '' },
      reuseExistingServer: false,
    },
  ],
})
