import { readFile } from 'node:fs/promises';
const env = await readFile(new URL('../.runtime/local.env', import.meta.url), 'utf8');
const password = env.match(/^BAOYAN_ADMIN_PASSWORD=(.+)$/m)?.[1].trim();
if (!password) throw new Error('Local admin password missing');
const configUrl = 'http://127.0.0.1:28848/nacos/v1/cs/configs';
const query = new URLSearchParams({dataId:'baoyan-platform.yaml', group:'BAOYAN_GROUP'});
const existing = await fetch(`${configUrl}?${query}`, {signal:AbortSignal.timeout(15000)});
if (existing.ok && (await existing.text()).trim()) {
  console.log('Existing local Nacos configuration preserved');
  process.exit(0);
}
if (!existing.ok && existing.status !== 404) throw new Error(`Cannot check existing Nacos configuration: ${existing.status}`);
const content = `baoyan:
  application:
    admin-password: "${password}"
    public-base-url: "http://localhost:18081"
  storage:
    bucket: baoyan
  tasks:
    default-timezone: Asia/Shanghai
    reminder-poll-seconds: 30
`;
const body = new URLSearchParams({dataId:'baoyan-platform.yaml', group:'BAOYAN_GROUP', type:'yaml', content});
const r = await fetch(configUrl, {method:'POST', body, signal:AbortSignal.timeout(15000)});
if (!r.ok || (await r.text()).trim() !== 'true') throw new Error('Could not initialize local Nacos config');
console.log('Local Nacos configuration initialized');
