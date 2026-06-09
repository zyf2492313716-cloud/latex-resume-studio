#!/usr/bin/env node
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const projectDir = path.resolve(__dirname, '..');
const libsDir = path.join(projectDir, 'src', 'utils', 'libs');
const stagingDir = path.join(projectDir, 'src', 'utils', `.libs-staging-${process.pid}`);
const runtimeRequirements = path.join(projectDir, 'requirements-runtime.txt');
const requirements = fs.existsSync(runtimeRequirements) ? runtimeRequirements : path.join(projectDir, 'requirements.txt');

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: projectDir,
    stdio: 'inherit',
    encoding: 'utf8',
    shell: false,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} ${args.join(' ')} failed with exit ${result.status}`);
}

function findPython() {
  const candidates = process.platform === 'win32'
    ? [['py', ['-3']], ['python', []], ['python3', []]]
    : [['python3', []], ['python', []]];

  for (const [command, prefixArgs] of candidates) {
    const result = spawnSync(command, [...prefixArgs, '-c', 'import sys; print(sys.executable)'], {
      cwd: projectDir,
      encoding: 'utf8',
      stdio: 'pipe',
      shell: false,
    });
    if (result.status === 0) return { command, prefixArgs };
  }
  throw new Error('No Python 3 executable found. Install Python 3 and ensure it is on PATH.');
}

function rmrf(target) {
  fs.rmSync(target, { recursive: true, force: true });
}

function walk(dir, visitor) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full, visitor);
      visitor(full, true);
    } else {
      visitor(full, false);
    }
  }
}

function cleanup() {
  walk(stagingDir, (full, isDir) => {
    const base = path.basename(full);
    if (isDir && ['__pycache__', 'tests', 'test'].includes(base)) rmrf(full);
    if (isDir && (base.endsWith('.dist-info') || base.endsWith('.egg-info'))) rmrf(full);
    if (!isDir && (base.endsWith('.pyc') || base.endsWith('.pyo'))) fs.rmSync(full, { force: true });
  });
}

function directorySize(dir) {
  let total = 0;
  walk(dir, (full, isDir) => {
    if (!isDir) total += fs.statSync(full).size;
  });
  return total;
}

const python = findPython();
console.log(`Installing Python dependencies with ${python.command} ${python.prefixArgs.join(' ')}`.trim());
console.log(`Target: ${libsDir}`);

rmrf(stagingDir);
fs.mkdirSync(stagingDir, { recursive: true });

try {
  run(python.command, [
    ...python.prefixArgs,
    '-m',
    'pip',
    'install',
    '-r',
    requirements,
    '-t',
    stagingDir,
    '--only-binary=:all:',
    '--retries',
    '8',
    '--timeout',
    '60',
    '--quiet',
  ]);

  cleanup();

  rmrf(libsDir);
  fs.renameSync(stagingDir, libsDir);

  const mb = directorySize(libsDir) / 1024 / 1024;
  console.log(`Done. libs size: ${mb.toFixed(1)} MB`);
  console.log(fs.readdirSync(libsDir).sort().join('\n'));
} catch (err) {
  rmrf(stagingDir);
  throw err;
}
