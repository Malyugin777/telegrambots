import {
  List,
  useTable,
  EditButton,
  ShowButton,
  DeleteButton,
  TagField,
} from '@refinedev/antd';
import { Table, Space, Select, Button, Progress, message, Tooltip } from 'antd';
import {
  PlayCircleOutlined,
  StopOutlined,
  ReloadOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { useCustomMutation, useNavigation } from '@refinedev/core';
import { useState } from 'react';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';

interface Broadcast {
  id: number;
  name: string;
  text: string;
  status: 'draft' | 'scheduled' | 'running' | 'completed' | 'cancelled';
  target_type: string;
  total_recipients: number;
  sent_count: number;
  delivered_count: number;
  failed_count: number;
  scheduled_at: string | null;
  created_at: string;
}

const statusColors: Record<string, string> = {
  draft: 'default',
  scheduled: 'blue',
  running: 'processing',
  completed: 'green',
  cancelled: 'red',
};

const statusLabels: Record<string, string> = {
  draft: 'Черновик',
  scheduled: 'Запланирована',
  running: 'Выполняется',
  completed: 'Завершена',
  cancelled: 'Отменена',
};

const targetLabels: Record<string, string> = {
  all: 'Все',
  segment: 'Сегмент',
  list: 'Список',
};

export const BroadcastList = () => {
  const { t } = useTranslation();
  const { create } = useNavigation();
  const [statusFilter, setStatusFilter] = useState<string | undefined>();

  const { tableProps, tableQueryResult } = useTable<Broadcast>({
    resource: 'broadcasts',
    syncWithLocation: true,
    filters: {
      permanent: statusFilter
        ? [{ field: 'status_filter', operator: 'eq' as const, value: statusFilter }]
        : [],
    },
  });

  const { mutate: startBroadcast, isLoading: isStarting } = useCustomMutation();
  const { mutate: cancelBroadcast, isLoading: isCancelling } = useCustomMutation();

  const handleStart = (id: number) => {
    startBroadcast(
      {
        url: `/broadcasts/${id}/start`,
        method: 'post',
        values: {},
      },
      {
        onSuccess: () => {
          message.success('Рассылка запущена');
          tableQueryResult.refetch();
        },
        onError: () => {
          message.error('Ошибка запуска рассылки');
        },
      }
    );
  };

  const handleCancel = (id: number) => {
    cancelBroadcast(
      {
        url: `/broadcasts/${id}/cancel`,
        method: 'post',
        values: {},
      },
      {
        onSuccess: () => {
          message.success('Рассылка отменена');
          tableQueryResult.refetch();
        },
        onError: () => {
          message.error('Ошибка отмены рассылки');
        },
      }
    );
  };

  return (
    <List
      headerButtons={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => create('broadcasts')}>
          Новая рассылка
        </Button>
      }
    >
      <Space style={{ marginBottom: 16 }}>
        <Select
          placeholder="Статус"
          style={{ width: 150 }}
          allowClear
          value={statusFilter}
          onChange={setStatusFilter}
          options={[
            { label: 'Черновик', value: 'draft' },
            { label: 'Запланирована', value: 'scheduled' },
            { label: 'Выполняется', value: 'running' },
            { label: 'Завершена', value: 'completed' },
            { label: 'Отменена', value: 'cancelled' },
          ]}
        />
        <Button
          icon={<ReloadOutlined />}
          onClick={() => tableQueryResult.refetch()}
        >
          Обновить
        </Button>
      </Space>

      <Table {...tableProps} rowKey="id">
        <Table.Column dataIndex="id" title="ID" width={60} />
        <Table.Column dataIndex="name" title="Название" />
        <Table.Column
          dataIndex="target_type"
          title="Аудитория"
          width={100}
          render={(value: string) => targetLabels[value] || value}
        />
        <Table.Column
          dataIndex="status"
          title="Статус"
          width={120}
          render={(value: string) => (
            <TagField color={statusColors[value] || 'default'} value={statusLabels[value] || value} />
          )}
        />
        <Table.Column
          title="Прогресс"
          width={200}
          render={(_, record: Broadcast) => {
            if (record.total_recipients === 0) return '-';
            const percent = Math.round((record.sent_count / record.total_recipients) * 100);
            return (
              <Tooltip title={`Доставлено: ${record.delivered_count}, Ошибок: ${record.failed_count}`}>
                <Space direction="vertical" size={0} style={{ width: '100%' }}>
                  <Progress
                    percent={percent}
                    size="small"
                    status={record.status === 'running' ? 'active' : undefined}
                  />
                  <span style={{ fontSize: 11, color: '#888' }}>
                    {record.delivered_count}/{record.total_recipients}
                  </span>
                </Space>
              </Tooltip>
            );
          }}
        />
        <Table.Column
          dataIndex="scheduled_at"
          title="Запуск"
          width={130}
          render={(value) =>
            value ? dayjs(value).format('DD.MM.YY HH:mm') : '-'
          }
        />
        <Table.Column
          title="Действия"
          width={150}
          render={(_, record: Broadcast) => (
            <Space>
              <ShowButton hideText size="small" recordItemId={record.id} />
              {(record.status === 'draft' || record.status === 'scheduled') && (
                <>
                  <EditButton hideText size="small" recordItemId={record.id} />
                  <Button
                    size="small"
                    type="primary"
                    icon={<PlayCircleOutlined />}
                    loading={isStarting}
                    onClick={() => handleStart(record.id)}
                    title="Запустить"
                  />
                  <DeleteButton hideText size="small" recordItemId={record.id} />
                </>
              )}
              {record.status === 'running' && (
                <Button
                  size="small"
                  danger
                  icon={<StopOutlined />}
                  loading={isCancelling}
                  onClick={() => handleCancel(record.id)}
                  title="Отменить"
                />
              )}
            </Space>
          )}
        />
      </Table>
    </List>
  );
};
