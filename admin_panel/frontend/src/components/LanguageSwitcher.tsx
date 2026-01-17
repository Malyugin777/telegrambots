import { Dropdown, Button, Space } from 'antd';
import { GlobalOutlined, DownOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { MenuProps } from 'antd';

const languages = [
  { key: 'ru', label: 'Русский', flag: '🇷🇺' },
  { key: 'en', label: 'English', flag: '🇺🇸' },
];

export const LanguageSwitcher = () => {
  const { i18n } = useTranslation();

  const currentLang = languages.find((l) => l.key === i18n.language) || languages[0];

  const items: MenuProps['items'] = languages.map((lang) => ({
    key: lang.key,
    label: (
      <Space>
        <span>{lang.flag}</span>
        <span>{lang.label}</span>
      </Space>
    ),
    onClick: () => i18n.changeLanguage(lang.key),
  }));

  return (
    <Dropdown menu={{ items }} trigger={['click']}>
      <Button type="text" style={{ color: 'rgba(255, 255, 255, 0.85)' }}>
        <Space>
          <GlobalOutlined />
          <span>{currentLang.flag}</span>
          <span>{currentLang.label}</span>
          <DownOutlined />
        </Space>
      </Button>
    </Dropdown>
  );
};
