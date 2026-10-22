import { copyFile, mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const siteRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const repoRoot = path.resolve(siteRoot, '..');
const sourceDir = path.join(repoRoot, 'docs');
const outputDir = path.join(siteRoot, 'src', 'content', 'docs');

const descriptions = {
  '../CHANGELOG.md': 'Remnawave Minishop 的发布历史、版本日期及开发分支变更。',
  'api/index.md': '网站和后台 HTTP API、OpenAPI 规范、域事件与扩展入口。',
  'index.md': '本项目中文文档入口：一期范围、进度、使用流程和验收边界。',
  'getting-started/overview.md': '项目组件及用户和管理员的一期流程。',
  'getting-started/system-requirements.md': 'VPS、Docker、网络和外部依赖的系统要求。',
  'getting-started/setup.md': '通过安装向导和 Docker Compose 启动 Minishop。',
  'getting-started/configuration.md': '初次配置 .env、登录密钥和网页管理后台。',
  'getting-started/deployment.md': 'Docker Compose、反向代理、TLS、镜像、更新和备份。',
  'configuration/security.md': '密钥、公开地址、管理员权限及 Minishop 安全基础。',
  'configuration/env-vars.md': 'Remnawave Minishop 环境变量完整参考。',
  'features/minishop-pro.md': 'minishop PRO 的公开业务分析、客户分群和销售自动化能力。',
  'features/payments.md': '支付方式、按钮、币种、收据及回调的上游配置说明。',
  'features/gifts.md': '上游赠送订阅的购买、转赠、激活和管理。',
  'features/promocodes.md': '激活码的奖励、折扣、购买应用和使用历史。',
  'features/partner-program.md': '合作伙伴申请、归因、佣金、余额和人工结算。',
  'features/subscriptions.md': 'Minishop 上游套餐、限额和订阅生命周期概览。',
  'features/notifications.md': 'Telegram 与邮件的用户、管理员和服务通知。',
  'features/tariffs.md': '上游套餐目录、周期、价格、流量和设备限额。',
  'features/web-app.md': 'Mini App、公开教程、代理和推荐链接。',
  'features/server-status.md': 'Mini App 中外部或内嵌的服务器状态。',
  'features/login-methods.md': '邮箱、Telegram、Google、Yandex 和通行密钥的配置与账号关联。',
  'features/telegram-optional.md': '使用邮箱登录和管理员角色的独立网页模式。',
  'features/webapp-themes.md': '自定义主题、CSS 变量、素材和主题制作。',
  'features/advertising/index.md': '广告功能概览及开发环境入门。',
  'features/advertising/glossary.md': '广告事件、用户和财务指标术语。',
  'features/advertising/campaigns-links.md': '活动、归档、Web／Bot／Mini App 链接和 UTM。',
  'features/advertising/attribution-auth.md': '匿名访问、登录、首次接触和订单来源。',
  'features/advertising/promocodes.md': '优惠版本、手动输入与激活码统计。',
  'features/advertising/telegram-ads-import.md': 'Telegram 广告 CSV 字段映射、修订与匹配限制。',
  'features/advertising/reporting.md': '币种、支出、购买、退款和用户群组成熟度。',
  'features/advertising/troubleshooting-limitations.md': '广告链接排障与历史数据限制。',
  'features/advertising/api-examples.md': '广告 API 契约及合成 CSV 示例。',
  'features/admin-panel.md': '管理后台中的用户、设置、套餐和客服管理。',
  'features/backups.md': '自动备份、Telegram 发送、本地留存及后台恢复。',
  'features/support.md': '客服工单、后台处理、通知和限制。',
  'migrations/index.md': '从其他机器人迁移至 Remnawave Minishop 的方案。',
  'migrations/remnawave-tg-shop.md': '将 remnawave-tg-shop 数据迁移到 Minishop。',
  'migrations/remnashop.md': '通过安装向导或脚本导入 Remnashop 数据。',
  'migrations/bedolaga.md': '以可复核的试运行和财务对账导入 Bedolaga 数据。',
  'troubleshooting/issues.md': '启动、回调、Mini App 和支付的常见问题。',
  'troubleshooting/logs.md': '排查后端、worker、前端、迁移和回调日志。',
  'troubleshooting/maintenance.md': '生产环境的更新、迁移、备份与检查。',
  'architecture.md': '后端、前端、worker 和基础设施架构概览。',
  'architecture/http-api.md': 'HTTP 响应封装、鉴权、OpenAPI 和类型化路由规则。',
  'architecture/events.md': '域事件、载荷、触发者和 Core 反应目录。',
  'development/graphify.md': 'Graphify 代码图的使用和更新时机。',
};

const imageExtensions = new Set(['.avif', '.gif', '.jpeg', '.jpg', '.png', '.svg', '.webp']);
const inlineContentsMinHeadings = 8;
const inlineContentsMinLines = 180;

function yamlString(value) {
  return JSON.stringify(value);
}

function toPosix(relativePath) {
  return relativePath.split(path.sep).join('/');
}

function outputRelativePath(sourceRelativePath) {
  if (sourceRelativePath === '../CHANGELOG.md') {
    return 'changelog.md';
  }
  if (sourceRelativePath === 'index.md') {
    return 'index.md';
  }
  if (!sourceRelativePath.includes('/')) {
    return `reference/${sourceRelativePath}`;
  }
  return sourceRelativePath;
}

function pagePathForSource(sourceRelativePath, hash = '') {
  const output = outputRelativePath(sourceRelativePath).replace(/\.md$/i, '');
  const route = output === 'index' ? '/' : `/${output.replace(/\/index$/u, '')}/`;
  return `${route}${hash}`;
}

function titleForRelativePath(relativePath) {
  const baseName = path.posix.basename(relativePath, '.md');
  return baseName;
}

function extractTitle(relativePath, content) {
  const match = content.match(/^#\s+(.+?)\s*$/m);
  return match?.[1] ?? titleForRelativePath(relativePath);
}

function stripFirstHeading(content) {
  return content.replace(/^#\s+.+?\s*\r?\n+/, '');
}

function rewriteMarkdownLinks(markdown, sourceRelativePath) {
  const sourceDirectory = path.posix.dirname(sourceRelativePath);
  return markdown.replace(/\]\((?!https?:\/\/|mailto:|tel:|\/|#)([^)\s]+\.md)(#[^)]+)?\)/g, (match, target, hash = '') => {
    const resolvedTarget = path.posix.normalize(path.posix.join(sourceDirectory, target));
    const docsRelativeTarget = resolvedTarget.startsWith('../docs/')
      ? resolvedTarget.slice('../docs/'.length)
      : resolvedTarget;
    return `](${pagePathForSource(docsRelativeTarget, hash)})`;
  });
}

function normalizeCodeFences(markdown) {
  return markdown
    .replace(/^```env\s*$/gim, '```ini')
    .replace(/^```caddyfile\s*$/gim, '```txt');
}

function plainHeading(heading) {
  return heading
    .replace(/`([^`]+)`/gu, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/gu, '$1')
    .replace(/[*~]/gu, '')
    .trim();
}

function addInlineContents(markdown) {
  if (/^##\s+(?:导航|本页目录|参考目录|目录|Навигация по справочнику|На этой странице|Содержание|Оглавление)\s*$/imu.test(markdown)) {
    return markdown;
  }

  const headings = [...markdown.matchAll(/^##\s+(.+?)\s*$/gmu)];
  const lineCount = markdown.split(/\r?\n/u).length;
  if (headings.length < inlineContentsMinHeadings || lineCount < inlineContentsMinLines) {
    return markdown;
  }

  const slugOccurrences = new Map();
  const items = headings.map((match) => {
    const label = plainHeading(match[1]);
    const baseSlug = label
      .toLocaleLowerCase('zh-CN')
      .replace(/[^\p{L}\p{M}\p{N}_\-\s]/gu, '')
      .replace(/\s/gu, '-');
    const occurrence = slugOccurrences.get(baseSlug) ?? 0;
    slugOccurrences.set(baseSlug, occurrence + 1);
    const slug = occurrence === 0 ? baseSlug : `${baseSlug}-${occurrence}`;
    return `- [${label}](#${slug})`;
  });

  const firstHeadingIndex = headings[0].index;
  const before = markdown.slice(0, firstHeadingIndex).trimEnd();
  const after = markdown.slice(firstHeadingIndex).trimStart();
  return `${before}\n\n## 本页目录\n\n${items.join('\n')}\n\n${after}`;
}

function relatedLinksFor(sourceRelativePath) {
  const relatedByOverview = {
    'index.md': [
      ['更新日志', '/changelog/'],
      ['概览', '/getting-started/overview/'],
      ['快速开始', '/getting-started/setup/'],
      ['演示模式', '/getting-started/overview/#演示与验收边界'],
    ],
    'getting-started/overview.md': [
      ['快速开始', '/getting-started/setup/'],
      ['生产部署', '/getting-started/deployment/'],
      ['初始配置', '/getting-started/configuration/'],
      ['从其他机器人迁移', '/migrations/'],
    ],
    'getting-started/configuration.md': [
      ['.env 变量参考', '/configuration/env-vars/'],
      ['安全', '/configuration/security/'],
      ['网页管理后台', '/features/admin-panel/'],
    ],
    'configuration/security.md': [
      ['登录方式', '/features/login-methods/'],
      ['生产部署', '/getting-started/deployment/'],
      ['.env 变量参考', '/configuration/env-vars/'],
    ],
    'configuration/telemetry.md': [
      ['日志', '/troubleshooting/logs/'],
      ['维护', '/troubleshooting/maintenance/'],
      ['网页管理后台', '/features/admin-panel/'],
    ],
    'migrations/index.md': [
      ['从 remnawave-tg-shop 迁移', '/migrations/remnawave-tg-shop/'],
      ['从 Remnashop 迁移', '/migrations/remnashop/'],
      ['从 Bedolaga 迁移', '/migrations/bedolaga/'],
      ['快速开始', '/getting-started/setup/'],
    ],
    'features/payments.md': [
      ['支付变量', '/configuration/env-vars/#платежи'],
      ['套餐与订阅', '/features/subscriptions/'],
      ['查看日志排障', '/troubleshooting/logs/'],
    ],
    'features/subscriptions.md': [
      ['配置套餐', '/features/tariffs/'],
      ['支付', '/features/payments/'],
      ['网页应用', '/features/web-app/'],
    ],
    'features/login-methods.md': [
      ['安全', '/configuration/security/'],
      ['.env 变量参考', '/configuration/env-vars/#smtp-и-вход-по-email'],
      ['网页应用', '/features/web-app/'],
    ],
    'features/admin-panel.md': [
      ['备份', '/features/backups/'],
      ['遥测', '/configuration/telemetry/'],
      ['.env 变量参考', '/configuration/env-vars/'],
    ],
    'troubleshooting/logs.md': [
      ['常见问题', '/troubleshooting/issues/'],
      ['维护', '/troubleshooting/maintenance/'],
      ['遥测', '/configuration/telemetry/'],
    ],
    'troubleshooting/maintenance.md': [
      ['备份', '/features/backups/'],
      ['生产部署', '/getting-started/deployment/'],
      ['日志', '/troubleshooting/logs/'],
    ],
    'architecture.md': [
      ['API 概览', '/api/'],
      ['域事件', '/architecture/events/'],
      ['改动指南', '/development/how-to/'],
    ],
    'architecture/http-api.md': [
      ['API 概览', '/api/'],
      ['域事件', '/architecture/events/'],
      ['插件 API', '/development/plugins/'],
    ],
    'development/dev-stand.md': [
      ['改动指南', '/development/how-to/'],
      ['Graphify 代码图', '/development/graphify/'],
      ['Runes QA', '/development/runes-migration-qa/'],
    ],
    'development/how-to.md': [
      ['架构', '/reference/architecture/'],
      ['统一开发环境', '/development/dev-stand/'],
      ['Graphify 代码图', '/development/graphify/'],
    ],
    'development/graphify.md': [
      ['改动指南', '/development/how-to/'],
      ['架构', '/reference/architecture/'],
      ['统一开发环境', '/development/dev-stand/'],
    ],
    'development/runes-migration-qa.md': [
      ['统一开发环境', '/development/dev-stand/'],
      ['改动指南', '/development/how-to/'],
      ['Graphify 代码图', '/development/graphify/'],
    ],
    'api/index.md': [
      ['交互式接口规范', '/api/reference/'],
      ['HTTP 契约', '/architecture/http-api/'],
      ['插件 API', '/development/plugins/'],
    ],
  };

  return relatedByOverview[sourceRelativePath] ?? [];
}

function appendRelatedLinks(markdown, sourceRelativePath) {
  if (/^##\s+相关页面\s*$/mu.test(markdown)) {
    return markdown;
  }

  const currentRoute = pagePathForSource(sourceRelativePath);
  const links = relatedLinksFor(sourceRelativePath).filter(([, route]) => route !== currentRoute);
  if (links.length === 0) {
    return markdown;
  }

  const items = links.map(([label, route]) => `- [${label}](${route})`).join('\n');
  return `${markdown.trimEnd()}\n\n## 相关页面\n\n${items}\n`;
}

function extraFrontmatter(sourceRelativePath) {
  if (sourceRelativePath === '../CHANGELOG.md') {
    return ['tableOfContents:', '  minHeadingLevel: 2', '  maxHeadingLevel: 2'];
  }
  if (sourceRelativePath !== 'index.md') {
    return [];
  }

  return [
    'template: splash',
    'hero:',
    '  tagline: "一个账号管理多份独立服务：套餐、服务状态、人工开通与客户端教程。"',
    '  image:',
    '    html: \'<img class="minishop-hero-screenshot" src="/remnawave-minishop.webp" alt="Remnawave Minishop 界面" width="1920" height="1080" loading="eager" decoding="async" />\'',
    '  actions:',
    '    - text: "查看演示"',
    '      link: /demo/home',
    '      icon: right-arrow',
    '    - text: "了解 PRO"',
    '      link: https://cloud.minidoc.cc',
    '      variant: secondary',
    '    - text: "安装说明"',
    '      link: /getting-started/setup/',
    '      icon: setting',
    '      variant: minimal',
  ];
}

function frontmatter({ title, description, sourceRelativePath }) {
  const repositoryPath = sourceRelativePath === '../CHANGELOG.md'
    ? 'CHANGELOG.md'
    : `docs/${sourceRelativePath}`;
  const editPath = repositoryPath
    .split('/')
    .map((segment) => encodeURIComponent(segment))
    .join('/');
  const branch = process.env.DOCS_BRANCH ?? process.env.CF_PAGES_BRANCH ??
    process.env.CI_COMMIT_BRANCH ?? process.env.GITHUB_REF_NAME ??
    process.env.VERCEL_GIT_COMMIT_REF ?? process.env.BRANCH ?? 'main';
  const editUrl = `https://gitlab.com/3252a8/remnawave-minishop/-/edit/${encodeURIComponent(branch)}/${editPath}`;
  return [
    '---',
    `title: ${yamlString(title)}`,
    `description: ${yamlString(description)}`,
    `editUrl: ${yamlString(editUrl)}`,
    ...extraFrontmatter(sourceRelativePath),
    '---',
    '',
  ].join('\n');
}

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await walk(absolutePath)));
      continue;
    }
    if (entry.isFile()) {
      files.push(absolutePath);
    }
  }
  return files;
}

async function syncMarkdown(files) {
  for (const sourcePath of files.filter((file) => file.endsWith('.md'))) {
    const sourceRelativePath = toPosix(path.relative(sourceDir, sourcePath));
    const outputRelative = outputRelativePath(sourceRelativePath);
    const outputPath = path.join(outputDir, ...outputRelative.split('/'));
    const content = await readFile(sourcePath, 'utf8');
    const title = extractTitle(sourceRelativePath, content);
    const markdown = normalizeCodeFences(
      rewriteMarkdownLinks(stripFirstHeading(content).trimStart(), sourceRelativePath),
    );
    const body = appendRelatedLinks(
      sourceRelativePath === '../CHANGELOG.md' ? markdown : addInlineContents(markdown),
      sourceRelativePath,
    );
    const output = frontmatter({
      title,
      description: descriptions[sourceRelativePath] ?? title,
      sourceRelativePath,
    });

    await mkdir(path.dirname(outputPath), { recursive: true });
    await writeFile(outputPath, `${output}${body}\n`, 'utf8');
  }
}

async function syncAssets(files) {
  for (const sourcePath of files.filter((file) => imageExtensions.has(path.extname(file).toLowerCase()))) {
    const sourceRelativePath = toPosix(path.relative(sourceDir, sourcePath));
    const outputRelative = !sourceRelativePath.includes('/')
      ? sourceRelativePath
      : sourceRelativePath;
    const outputPath = path.join(outputDir, ...outputRelative.split('/'));
    await mkdir(path.dirname(outputPath), { recursive: true });
    await copyFile(sourcePath, outputPath);

    if (!sourceRelativePath.includes('/')) {
      const referenceOutputPath = path.join(outputDir, 'reference', sourceRelativePath);
      await mkdir(path.dirname(referenceOutputPath), { recursive: true });
      await copyFile(sourcePath, referenceOutputPath);
    }
  }
}

async function syncPublicArtifacts() {
  const publicDir = path.join(siteRoot, 'public');
  await Promise.all([
    copyFile(path.join(sourceDir, 'openapi.json'), path.join(publicDir, 'openapi.json')),
    copyFile(
      path.join(sourceDir, 'remnawave-minishop.webp'),
      path.join(publicDir, 'remnawave-minishop.webp'),
    ),
  ]);
}

await rm(outputDir, { recursive: true, force: true });
await mkdir(outputDir, { recursive: true });

const files = await walk(sourceDir);
await syncMarkdown([...files, path.join(repoRoot, 'CHANGELOG.md')]);
await syncAssets(files);
await syncPublicArtifacts();

console.log(`Synced documentation from ${path.relative(repoRoot, sourceDir)} to ${path.relative(repoRoot, outputDir)}`);
