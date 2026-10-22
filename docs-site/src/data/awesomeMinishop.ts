import copy from "../../../locales/zh-hans.json";

export interface CommunityProject {
  id: string;
  name: string;
  author: string;
  authorUrl: string;
  repository: string;
  forge: 'GitHub' | 'GitLab';
  preview: string;
  previewAlt: string;
  cover?: boolean;
  description: string;
  tags: string[];
  details: string[];
  install?: { repository: string; branch: string; directory?: string };
}

export interface CommunityCategory {
  id: string;
  title: string;
  icon: string;
  description: string;
  guide: { label: string; href: string };
  projects: CommunityProject[];
}

export const communityCategories: CommunityCategory[] = [
  {
    id: 'themes',
    title: copy.docs_catalog_themes_title,
    icon: 'themes',
    description: copy.docs_catalog_themes_description,
    guide: { label: copy.docs_catalog_themes_guide, href: '/features/theme-packages/' },
    projects: [
      {
        id: 'aurora',
        name: 'Aurora',
        author: 'austnv',
        authorUrl: 'https://github.com/austnv',
        repository: 'https://github.com/austnv/minishop-themes/tree/master/themes/aurora',
        forge: 'GitHub',
        preview: '/awesome/aurora.webp',
        previewAlt: copy.docs_catalog_aurora_alt,
        description: copy.docs_catalog_aurora_description,
        tags: [copy.docs_catalog_aurora_tag_1, copy.docs_catalog_aurora_tag_2],
        details: [copy.docs_catalog_aurora_detail_1, copy.docs_catalog_aurora_detail_2],
        install: { repository: 'https://github.com/austnv/minishop-themes', branch: 'master', directory: 'themes/aurora' },
      },
      {
        id: 'solar',
        name: 'Solar',
        author: 'austnv',
        authorUrl: 'https://github.com/austnv',
        repository: 'https://github.com/austnv/minishop-themes/tree/master/themes/solar',
        forge: 'GitHub',
        preview: '/awesome/solar.webp',
        previewAlt: copy.docs_catalog_solar_alt,
        description: copy.docs_catalog_solar_description,
        tags: [copy.docs_catalog_solar_tag_1, copy.docs_catalog_solar_tag_2],
        details: [copy.docs_catalog_solar_detail_1, copy.docs_catalog_solar_detail_2],
        install: { repository: 'https://github.com/austnv/minishop-themes', branch: 'master', directory: 'themes/solar' },
      },
      {
        id: 'universe',
        name: 'Universe',
        author: 'austnv',
        authorUrl: 'https://github.com/austnv',
        repository: 'https://github.com/austnv/minishop-themes/tree/master/themes/universe',
        forge: 'GitHub',
        preview: '/awesome/universe.webp',
        previewAlt: copy.docs_catalog_universe_alt,
        description: copy.docs_catalog_universe_description,
        tags: [copy.docs_catalog_universe_tag_1, copy.docs_catalog_universe_tag_2],
        details: [copy.docs_catalog_universe_detail_1, copy.docs_catalog_universe_detail_2],
        install: { repository: 'https://github.com/austnv/minishop-themes', branch: 'master', directory: 'themes/universe' },
      },
      {
        id: 'liquid-glass',
        name: 'Liquid Glass',
        author: 'BADtochka',
        authorUrl: 'https://github.com/BADtochka',
        repository: 'https://github.com/BADtochka/liquid-glass-minishop-theme/tree/main',
        forge: 'GitHub',
        preview: '/awesome/liquid-glass.webp',
        previewAlt: copy.docs_catalog_liquid_glass_alt,
        description: copy.docs_catalog_liquid_glass_description,
        tags: ['Glass UI', copy.docs_catalog_liquid_glass_tag_2],
        details: [copy.docs_catalog_liquid_glass_detail_1, copy.docs_catalog_liquid_glass_detail_2],
        install: { repository: 'https://github.com/BADtochka/liquid-glass-minishop-theme', branch: 'main' },
      },
      {
        id: 'avio-soft',
        name: 'Avio Soft',
        author: 'drobyazkome',
        authorUrl: 'https://github.com/drobyazkome',
        repository: 'https://github.com/drobyazkome/avio-soft-minishop-theme',
        forge: 'GitHub',
        preview: '/awesome/avio-soft.webp',
        previewAlt: copy.docs_catalog_avio_soft_alt,
        description: copy.docs_catalog_avio_soft_description,
        tags: [copy.docs_catalog_avio_soft_tag_1, copy.docs_catalog_avio_soft_tag_2],
        details: [copy.docs_catalog_avio_soft_detail_1, copy.docs_catalog_avio_soft_detail_2],
        install: { repository: 'https://github.com/drobyazkome/avio-soft-minishop-theme', branch: 'main' },
      },
      {
        id: 'avio',
        name: 'Avio',
        author: 'drobyazkome',
        authorUrl: 'https://github.com/drobyazkome',
        repository: 'https://github.com/drobyazkome/avio-minishop-theme',
        forge: 'GitHub',
        preview: '/awesome/avio.webp',
        previewAlt: copy.docs_catalog_avio_alt,
        description: copy.docs_catalog_avio_description,
        tags: [copy.docs_catalog_avio_tag_1, copy.docs_catalog_avio_tag_2],
        details: [copy.docs_catalog_avio_detail_1, copy.docs_catalog_avio_detail_2],
        install: { repository: 'https://github.com/drobyazkome/avio-minishop-theme', branch: 'main' },
      },
      {
        id: 'cyberpunk2077',
        name: 'Cyberpunk 2077',
        author: 'wormy09',
        authorUrl: 'https://gitlab.com/wormy09',
        repository: 'https://gitlab.com/wormy09/minishop-theme-cyberpunk2077/-/tree/main',
        forge: 'GitLab',
        preview: '/awesome/cyberpunk2077.webp',
        previewAlt: copy.docs_catalog_cyberpunk_alt,
        description: copy.docs_catalog_cyberpunk_description,
        tags: [copy.docs_catalog_cyberpunk_tag_1, copy.docs_catalog_cyberpunk_tag_2],
        details: [copy.docs_catalog_cyberpunk_detail_1, copy.docs_catalog_cyberpunk_detail_2],
        install: { repository: 'https://gitlab.com/wormy09/minishop-theme-cyberpunk2077', branch: 'main' },
      },
    ],
  },
  {
    id: 'plugins',
    title: copy.docs_catalog_plugins_title,
    icon: 'plugins',
    description: copy.docs_catalog_plugins_description,
    guide: { label: copy.docs_catalog_plugins_guide, href: '/development/plugins/' },
    projects: [
      {
        id: 'kiro-wheel',
        name: 'Kiro Wheel',
        author: 'kiroproject',
        authorUrl: 'https://github.com/kiroproject',
        repository: 'https://github.com/kiroproject/kiro-wheel',
        forge: 'GitHub',
        preview: '/awesome/kiro-wheel.svg',
        previewAlt: copy.docs_catalog_kiro_alt,
        cover: true,
        description: copy.docs_catalog_kiro_description,
        tags: [copy.docs_catalog_kiro_tag_1, copy.docs_catalog_kiro_tag_2],
        details: [copy.docs_catalog_kiro_detail_1, copy.docs_catalog_kiro_detail_2],
      },
    ],
  },
  {
    id: 'tools',
    title: copy.docs_catalog_tools_title,
    icon: 'tools',
    description: copy.docs_catalog_tools_description,
    guide: { label: copy.docs_catalog_tools_guide, href: '/features/support/' },
    projects: [
      {
        id: 'ai-support',
        name: 'AI Support',
        author: 'tagashi666',
        authorUrl: 'https://github.com/tagashi666',
        repository: 'https://github.com/tagashi666/ai-support',
        forge: 'GitHub',
        preview: '/awesome/ai-support.svg',
        previewAlt: copy.docs_catalog_ai_support_alt,
        cover: true,
        description: copy.docs_catalog_ai_support_description,
        tags: [copy.docs_catalog_ai_support_tag_1, copy.docs_catalog_ai_support_tag_2],
        details: [copy.docs_catalog_ai_support_detail_1, copy.docs_catalog_ai_support_detail_2],
      },
    ],
  },
];

// Public API snapshot, used until the browser refreshes the count or when offline.
export const starsVerifiedAt = '2026-10-02';
export const repositoryStars: Record<string, number> = {
  'austnv/minishop-themes': 1,
  'BADtochka/liquid-glass-minishop-theme': 0,
  'drobyazkome/avio-soft-minishop-theme': 1,
  'drobyazkome/avio-minishop-theme': 0,
  'kiroproject/kiro-wheel': 0,
  'tagashi666/ai-support': 25,
  'wormy09/minishop-theme-cyberpunk2077': 0,
};
