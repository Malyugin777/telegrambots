import { List, useTable, ShowButton, TagField } from '@refinedev/antd';
import { Table, Space, Input, Select, Button, Switch, message, Tabs } from 'antd';
import { SearchOutlined, ReloadOutlined, GiftOutlined } from '@ant-design/icons';
import { useUpdate, useCustom } from '@refinedev/core';
import { useState } from 'react';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import { ExportButton } from '../../components';

interface FreeDownloader {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  free_youtube_full_count: number;
  total_youtube_full_count: number;
}

interface User {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  language_code: string | null;
  role: 'user' | 'moderator' | 'admin' | 'owner';
  is_banned: boolean;
  ban_reason: string | null;
  created_at: string;
  last_active_at: string | null;
  downloads_count: number;
}

const roleColors: Record<string, string> = {
  user: 'default',
  moderator: 'blue',
  admin: 'purple',
  owner: 'gold',
};

export const UserList = () => {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<string | undefined>();
  const [bannedFilter, setBannedFilter] = useState<boolean | undefined>();
  const [activeTab, setActiveTab] = useState('all');

  const { tableProps, tableQueryResult } = useTable<User>({
    resource: 'users',
    syncWithLocation: true,
    filters: {
      permanent: [
        ...(search ? [{ field: 'search', operator: 'eq' as const, value: search }] : []),
        ...(roleFilter ? [{ field: 'role', operator: 'eq' as const, value: roleFilter }] : []),
        ...(bannedFilter !== undefined ? [{ field: 'is_banned', operator: 'eq' as const, value: bannedFilter }] : []),
      ],
    },
  });

  // Данные о бесплатных качальщиках
  const { data: freeDownloadersData, isLoading: freeLoading, refetch: refetchFree } = useCustom<FreeDownloader[]>({
    url: '/users/top-free-downloaders',
    method: 'get',
    config: {
      query: { limit: 50 },
    },
    queryOptions: {
      enabled: activeTab === 'free',  // Загружаем только когда активна вкладка
    },
  });
  const freeDownloaders = freeDownloadersData?.data || [];

  return (
    <List>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'all',
            label: 'Все пользователи',
          },
          {
            key: 'free',
            label: (
              <span>
                <GiftOutlined style={{ color: '#faad14' }} /> Бесплатные качальщики
              </span>
            ),
          },
        ]}
        style={{ marginBottom: 16 }}
      />

      {activeTab === 'all' && (
        <>
          <Space style={{ marginBottom: 16 }}>
            <Input
              placeholder={t('users.searchUsers')}
              prefix={<SearchOutlined />}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: 200 }}
              allowClear
            />
            <Select
              placeholder={t('users.role.title')}
              style={{ width: 130 }}
              allowClear
              value={roleFilter}
              onChange={setRoleFilter}
              options={[
                { label: t('users.role.user'), value: 'user' },
                { label: t('users.role.moderator'), value: 'moderator' },
                { label: t('users.role.admin'), value: 'admin' },
                { label: t('users.role.owner'), value: 'owner' },
              ]}
            />
            <Select
              placeholder={t('users.banStatus')}
              style={{ width: 130 }}
              allowClear
              value={bannedFilter}
              onChange={setBannedFilter}
              options={[
                { label: t('users.banned'), value: true },
                { label: t('bots.status.active'), value: false },
              ]}
            />
            <Button
              icon={<ReloadOutlined />}
              onClick={() => tableQueryResult.refetch()}
            >
              {t('common.refresh')}
            </Button>
            <ExportButton
              resource="users"
              filters={{ role: roleFilter, is_banned: bannedFilter }}
            />
          </Space>

          <Table {...tableProps} rowKey="id">
            <Table.Column dataIndex="id" title={t('common.id')} width={80} />
            <Table.Column
              dataIndex="telegram_id"
              title={t('users.telegramId')}
              render={(value) => <code>{value}</code>}
            />
            <Table.Column
              dataIndex="username"
              title={t('users.username')}
              render={(value) => (value ? `@${value}` : '-')}
            />
            <Table.Column
              title={t('users.fullName')}
              render={(_, record: User) =>
                [record.first_name, record.last_name].filter(Boolean).join(' ') || '-'
              }
            />
            <Table.Column
              dataIndex="role"
              title={t('users.role.title')}
              render={(value: string) => (
                <TagField color={roleColors[value] || 'default'} value={t(`users.role.${value}`)} />
              )}
            />
            <Table.Column
              dataIndex="is_banned"
              title={t('users.banned')}
              render={(value: boolean) => (
                <TagField color={value ? 'red' : 'green'} value={value ? t('common.yes') : t('common.no')} />
              )}
            />
            <Table.Column
              dataIndex="downloads_count"
              title={t('users.downloadsCount')}
              render={(value: number) => (
                <span style={{ color: '#52c41a', fontWeight: 500 }}>{value || 0}</span>
              )}
            />
            <Table.Column
              dataIndex="last_active_at"
              title={t('users.lastActive')}
              render={(value) =>
                value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'
              }
            />
            <Table.Column
              title={t('common.actions')}
              render={(_, record: User) => (
                <Space>
                  <ShowButton hideText size="small" recordItemId={record.id} />
                </Space>
              )}
            />
          </Table>
        </>
      )}

      {activeTab === 'free' && (
        <>
          <Space style={{ marginBottom: 16 }}>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => refetchFree()}
              loading={freeLoading}
            >
              {t('common.refresh')}
            </Button>
            <span style={{ color: '#888' }}>
              Юзеры, скачавшие YouTube Full без показа рекламы (flyer_required=false)
            </span>
          </Space>

          <Table
            dataSource={freeDownloaders}
            loading={freeLoading}
            rowKey="id"
            pagination={{ pageSize: 20 }}
          >
            <Table.Column dataIndex="id" title={t('common.id')} width={80} />
            <Table.Column
              dataIndex="telegram_id"
              title={t('users.telegramId')}
              render={(value) => <code>{value}</code>}
            />
            <Table.Column
              dataIndex="username"
              title={t('users.username')}
              render={(value) => (value ? `@${value}` : '-')}
            />
            <Table.Column
              dataIndex="first_name"
              title="Имя"
              render={(value) => value || '-'}
            />
            <Table.Column
              dataIndex="free_youtube_full_count"
              title="Бесплатно"
              render={(value: number) => (
                <span style={{ color: '#faad14', fontWeight: 'bold' }}>⚠️ {value}</span>
              )}
            />
            <Table.Column
              dataIndex="total_youtube_full_count"
              title="Всего YT Full"
              render={(value: number) => (
                <span style={{ color: '#1890ff' }}>{value}</span>
              )}
            />
            <Table.Column
              title={t('common.actions')}
              render={(_, record: FreeDownloader) => (
                <Space>
                  <ShowButton hideText size="small" recordItemId={record.id} />
                </Space>
              )}
            />
          </Table>
        </>
      )}
    </List>
  );
};
