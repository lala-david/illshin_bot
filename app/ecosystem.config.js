module.exports = {
  apps: [{
    name: "일신봇",
    script: "bot.py",
    interpreter: "python",
    cwd: __dirname,
    autorestart: true,
    max_restarts: 10,
    restart_delay: 5000,
    error_file: "logs/error.log",
    out_file: "logs/output.log",
    merge_logs: true
  }]
};
