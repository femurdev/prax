const path = require('path');

const backendDir = path.join(__dirname, 'backend');
const isWin = process.platform === 'win32';
const startScript = isWin
  ? path.join(__dirname, 'scripts', 'start-backend.cmd')
  : path.join(__dirname, 'scripts', 'start-backend.sh');

module.exports = {
  apps: [
    {
      name: 'prax-backend',
      cwd: backendDir,
      script: startScript,
      interpreter: isWin ? 'cmd' : 'bash',
      interpreter_args: isWin ? ['/c'] : [],
      watch: false,
      env: {
        NODE_ENV: 'development',
      },
      error_file: path.join(__dirname, 'logs', 'prax-backend-error.log'),
      out_file: path.join(__dirname, 'logs', 'prax-backend-out.log'),
    },
  ],
};
