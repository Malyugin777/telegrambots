import { useState } from 'react';
import { List, useTable, SaveButton } from '@refinedev/antd';
import { useUpdate, useList } from '@refinedev/core';
import { Table, Select, Input, Button, Space, Tag, message, Card } from 'antd';
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons';

const { TextArea } = Input;

interface BotMessage {
  id: number;
  bot_id: number;
  message_key: string;
  text_ru: string;
  text_en: string | null;
  is_active: boolean;
  updated_at: string;
  bot_name: string;
}

interface Bot {
  id: number;
  name: string;
}

const messageKeyLabels: Record<string, string> = {
  start: 'Приветствие (/start)',
  help: 'Помощь (/help)',
  downloading: 'Загрузка...',
  success: 'Успех',
  error_not_found: 'Ошибка: не найдено',
  error_timeout: 'Ошибка: таймаут',
  error_too_large: 'Ошибка: файл большой',
  error_unknown: 'Ошибка: неизвестная',
};

export const BotMessageList = () => {
  const [selectedBotId, setSelectedBotId] = useState<number | undefined>();
  const [editedMessages, setEditedMessages] = useState<Record<number, Partial<BotMessage>>>({});
  const { mutate: updateMessage, isLoading: isUpdating } = useUpdate();

  // Fetch bots for filter
  const { data: botsData } = useList<Bot>({
    resource: 'bots',
    pagination: { mode: 'off' },
  });
  const bots = botsData?.data || [];

  const { tableProps, tableQueryResult } = useTable<BotMessage>({
    resource: 'bot-messages',
    syncWithLocation: false,
    pagination: { mode: 'off' },
    filters: {
      permanent: selectedBotId ? [{ field: 'bot_id', operator: 'eq', value: selectedBotId }] : [],
    },
  });

  const handleTextChange = (id: number, field: 'text_ru' | 'text_en', value: string) => {
    setEditedMessages(prev => ({
      ...prev,
      [id]: { ...prev[id], [field]: value },
    }));
  };

  const handleSave = async (record: BotMessage) => {
    const changes = editedMessages[record.id];
    if (!changes) return;

    updateMessage(
      {
        resource: 'bot-messages',
        id: record.id,
        values: changes,
      },
      {
        onSuccess: () => {
          message.success('Сообщение сохранено');
          setEditedMessages(prev => {
            const newState = { ...prev };
            delete newState[record.id];
            return newState;
          });
          tableQueryResult.refetch();
        },
        onError: () => {
          message.error('Ошибка сохранения');
        },
      }
    );
  };

  const handleSaveAll = async () => {
    const ids = Object.keys(editedMessages).map(Number);
    for (const id of ids) {
      const record = tableQueryResult.data?.data.find((m: BotMessage) => m.id === id);
      if (record) {
        await handleSave(record);
      }
    }
  };

  const hasChanges = Object.keys(editedMessages).length > 0;

  return (
    <List
      title="Тексты бота"
      headerButtons={
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => tableQueryResult.refetch()}
          >
            Обновить
          </Button>
          {hasChanges && (
            <Button
              type="primary"
              icon={<SaveOutlined />}
              onClick={handleSaveAll}
              loading={isUpdating}
            >
              Сохранить все ({Object.keys(editedMessages).length})
            </Button>
          )}
        </Space>
      }
    >
      <Card style={{ marginBottom: 16 }}>
        <Space>
          <span>Бот:</span>
          <Select
            placeholder="Выберите бота"
            style={{ width: 250 }}
            allowClear
            value={selectedBotId}
            onChange={setSelectedBotId}
            options={bots.map(bot => ({ label: bot.name, value: bot.id }))}
          />
        </Space>
      </Card>

      <Table
        {...tableProps}
        rowKey="id"
        pagination={false}
        rowClassName={(record) => editedMessages[record.id] ? 'row-edited' : ''}
      >
        <Table.Column
          dataIndex="message_key"
          title="Ключ"
          width={200}
          render={(value: string) => (
            <Space direction="vertical" size={0}>
              <Tag color="blue">{value}</Tag>
              <span style={{ fontSize: 12, color: '#888' }}>
                {messageKeyLabels[value] || value}
              </span>
            </Space>
          )}
        />
        <Table.Column
          dataIndex="text_ru"
          title="Текст (RU)"
          render={(value: string, record: BotMessage) => (
            <TextArea
              value={editedMessages[record.id]?.text_ru ?? value}
              onChange={(e) => handleTextChange(record.id, 'text_ru', e.target.value)}
              autoSize={{ minRows: 2, maxRows: 6 }}
              style={{
                fontFamily: 'monospace',
                backgroundColor: editedMessages[record.id]?.text_ru !== undefined ? '#fffbe6' : undefined,
              }}
            />
          )}
        />
        <Table.Column
          dataIndex="text_en"
          title="Текст (EN)"
          render={(value: string | null, record: BotMessage) => (
            <TextArea
              value={editedMessages[record.id]?.text_en ?? value ?? ''}
              onChange={(e) => handleTextChange(record.id, 'text_en', e.target.value)}
              autoSize={{ minRows: 2, maxRows: 6 }}
              placeholder="English text (optional)"
              style={{
                fontFamily: 'monospace',
                backgroundColor: editedMessages[record.id]?.text_en !== undefined ? '#fffbe6' : undefined,
              }}
            />
          )}
        />
        <Table.Column
          dataIndex="is_active"
          title="Статус"
          width={100}
          render={(value: boolean) => (
            <Tag color={value ? 'green' : 'default'}>
              {value ? 'Активно' : 'Выкл'}
            </Tag>
          )}
        />
        <Table.Column
          title="Действия"
          width={120}
          render={(_, record: BotMessage) => (
            <Button
              type="primary"
              size="small"
              icon={<SaveOutlined />}
              disabled={!editedMessages[record.id]}
              loading={isUpdating}
              onClick={() => handleSave(record)}
            >
              Сохранить
            </Button>
          )}
        />
      </Table>

      <style>{`
        .row-edited {
          background-color: #fffbe6 !important;
        }
      `}</style>
    </List>
  );
};
