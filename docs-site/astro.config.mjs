import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightThemeNova from 'starlight-theme-nova';

const stableDocsUrl = 'https://minishop.minidoc.cc';
const devDocsUrl = 'https://dev.minishop.minidoc.cc';
const docsBranch =
  process.env.DOCS_BRANCH ??
  process.env.CF_PAGES_BRANCH ??
  process.env.CI_COMMIT_BRANCH ??
  process.env.GITHUB_REF_NAME ??
  process.env.VERCEL_GIT_COMMIT_REF ??
  process.env.BRANCH ??
  '';
const isDevDocs = docsBranch === 'dev';
const docsSiteUrl = isDevDocs ? devDocsUrl : stableDocsUrl;
const otherDocsVersion = isDevDocs
  ? { label: '查看稳定版文档', href: stableDocsUrl }
  : { label: '查看开发版文档', href: devDocsUrl };

export default defineConfig({
  site: docsSiteUrl,
  redirects: {
    '/features/core': '/getting-started/overview/',
    '/getting-started/demo': '/getting-started/overview/#演示与验收边界',
  },
  integrations: [
    starlight({
      title: 'minishop',
      favicon: '/favicon.png',
      description:
        'Remnawave Minishop 的配置、部署与运维文档。',
      plugins: [
        starlightThemeNova({
          nav: [
            { label: '演示', href: '/demo/home' },
            { label: '文档', href: '/getting-started/overview/' },
            { label: '更新日志', href: '/changelog/' },
            { label: 'minishop PRO', href: 'https://cloud.minidoc.cc' },
            { label: 'API', href: '/api/' },
            { label: 'GitHub', href: 'https://github.com/3252a8/remnawave-minishop' },
            { label: 'GitLab', href: 'https://gitlab.com/3252a8/remnawave-minishop' },
            { label: 'Telegram', href: 'https://t.me/remnawave_minishop' },
            otherDocsVersion,
          ],
        }),
      ],
      customCss: ['./src/styles/custom.css'],
      components: {
        Header: './src/components/Header.astro',
      },
      lastUpdated: false,
      locales: {
        root: {
          label: '简体中文',
          lang: 'zh-CN',
        },
      },
      head: [
        {
          tag: 'link',
          attrs: {
            rel: 'icon',
            href: '/favicon.webp',
            type: 'image/webp',
          },
        },
        {
          tag: 'meta',
          attrs: {
            name: 'theme-color',
            content: '#00fe7a',
          },
        },
        {
          tag: 'meta',
          attrs: {
            property: 'og:site_name',
            content: 'Remnawave Minishop Docs',
          },
        },
      ],
      sidebar: [
        {
          label: '我的 VPN · 二开项目',
          items: [
            { label: '需求基线', slug: 'reference/requirements' },
            { label: '产品设计', slug: 'reference/product-design' },
            { label: '架构评估', slug: 'reference/architecture-assessment' },
            { label: '实施计划', slug: 'reference/implementation-plan' },
            { label: '本地开发', slug: 'development/project-local' },
            { label: '独立服务接口', slug: 'development/independent-services' },
            { label: '连接与资源交付', slug: 'development/service-delivery' },

            { label: '权益与计量契约', slug: 'development/entitlement-metering-contract' },
            { label: '简体中文与体验', slug: 'development/chinese-localization' },
            { label: '客户端中文教程', slug: 'user-guide/clients-zh' },
          ],
        },
        {
          label: '开始使用',
          items: [
            { label: '首页', link: '/' },
            { label: '概览', slug: 'getting-started/overview' },
            { label: 'minishop PRO', slug: 'features/minishop-pro' },
            { label: '系统要求', slug: 'getting-started/system-requirements' },
            { label: '快速开始', slug: 'getting-started/setup' },
            { label: '生产部署', slug: 'getting-started/deployment' },
            { label: '初始配置', slug: 'getting-started/configuration' },
            {
              label: '从其他机器人迁移',
              collapsed: true,
              items: [
                { label: '概览', slug: 'migrations' },
                { label: 'remnawave-tg-shop', slug: 'migrations/remnawave-tg-shop' },
                { label: 'Remnashop', slug: 'migrations/remnashop' },
                { label: 'Bedolaga', slug: 'migrations/bedolaga' },
              ],
            },
          ],
        },
        {
          label: '功能',
          items: [
            {
              label: '销售与订阅',
              collapsed: false,
              items: [
                { label: '套餐与订阅', slug: 'features/subscriptions' },
                { label: '公开订阅网关', slug: 'architecture/subscription-gateway' },
                { label: '配置套餐', slug: 'features/tariffs' },
                { label: '支付', slug: 'features/payments' },
                { label: '赠送订阅', slug: 'features/gifts' },
                { label: '用户余额', slug: 'features/user-balance' },
                { label: '激活码', slug: 'features/promocodes' },
                { label: '合作伙伴计划', slug: 'features/partner-program' },
              ],
            },
            {
              label: '广告',
              collapsed: true,
              items: [
                { label: '广告概览', slug: 'features/advertising' },
                { label: '术语', slug: 'features/advertising/glossary' },
                { label: '活动与链接', slug: 'features/advertising/campaigns-links' },
                { label: '登录与来源', slug: 'features/advertising/attribution-auth' },
                { label: '优惠方案', slug: 'features/advertising/promocodes' },
                { label: '导入 Telegram 广告', slug: 'features/advertising/telegram-ads-import' },
                { label: '报表', slug: 'features/advertising/reporting' },
                { label: '核查与限制', slug: 'features/advertising/troubleshooting-limitations' },
        { label: 'API 与示例', slug: 'features/advertising/api-examples' },
              ],
            },
            { label: '网页应用', slug: 'features/web-app' },
            { label: '网页管理后台', slug: 'features/admin-panel' },
            { label: '登录方式', slug: 'features/login-methods' },
            { label: '不使用 Telegram', slug: 'features/telegram-optional' },
            { label: '主题与外观', slug: 'features/webapp-themes' },
            { label: '制作与发布主题', slug: 'features/theme-packages' },
            { label: '主题 JavaScript 效果', slug: 'features/theme-effects' },
            { label: '通知', slug: 'features/notifications' },
            { label: '客服与工单', slug: 'features/support' },
            { label: '服务器状态', slug: 'features/server-status' },
            { label: '备份', slug: 'features/backups' },
          ],
        },
        {
          label: '运维与诊断',
          collapsed: true,
          items: [
            { label: '.env 变量参考', slug: 'configuration/env-vars' },
            { label: '安全', slug: 'configuration/security' },
            { label: '遥测', slug: 'configuration/telemetry' },
            { label: '维护', slug: 'troubleshooting/maintenance' },
            { label: '常见问题', slug: 'troubleshooting/issues' },
            { label: '日志', slug: 'troubleshooting/logs' },
          ],
        },
        {
          label: 'API 与开发',
          collapsed: true,
          items: [
            { label: 'API 概览', slug: 'api' },
            { label: '交互式接口规范', link: '/api/reference/' },
            { label: 'HTTP 契约', slug: 'architecture/http-api' },
            {
              label: 'Remnawave API 兼容性',
              slug: 'architecture/remnawave-api-compatibility',
            },
            { label: '域事件', slug: 'architecture/events' },
            { label: '插件 API', slug: 'development/plugins' },
            { label: '扩展 SDK', slug: 'development/plugin-extensions' },
            { label: '插件页面与卡片', slug: 'development/plugin-ui-composition' },
            { label: '插件契约', slug: 'development/plugin-contract' },
            { label: '架构', slug: 'reference/architecture' },
            { label: '统一开发环境', slug: 'development/dev-stand' },
            { label: '测试环境', slug: 'reference/test-environments' },
            { label: '改动指南', slug: 'development/how-to' },
            { label: 'Graphify 代码图', slug: 'development/graphify' },
            { label: 'Runes QA', slug: 'development/runes-migration-qa' },
          ],
        },
        { label: 'Awesome Minishop', link: '/awesome-minishop/' },
        { label: '更新日志', slug: 'changelog' },
      ],
    }),
  ],
});
