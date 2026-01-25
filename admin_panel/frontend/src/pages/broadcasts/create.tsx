import { Create, useForm, useSelect } from '@refinedev/antd';
import { Form, Input, Select, DatePicker, Card, Row, Col, Divider, Button, Space, message } from 'antd';
import { PlusOutlined, MinusCircleOutlined, SendOutlined } from '@ant-design/icons';
import { useCreate, useCustomMutation, useNavigation } from '@refinedev/core';
import dayjs from 'dayjs';
import { useState } from 'react';
import { ImageUpload } from '../../components';

export const BroadcastCreate = () => {
  const { formProps, saveButtonProps, form } = useForm();
  const [targetType, setTargetType] = useState('all');
  const [sendingNow, setSendingNow] = useState(false);
  const { list } = useNavigation();

  const { mutateAsync: createBroadcast } = useCreate();
  const { mutateAsync: startBroadcast } = useCustomMutation();

  const { selectProps: botSelectProps } = useSelect({
    resource: 'bots',
    optionLabel: 'name',
    optionValue: 'id',
  });

  const handleSaveAndSend = async () => {
    try {
      setSendingNow(true);
      const values = await form.validateFields();

      // Create broadcast
      const result = await createBroadcast({
        resource: 'broadcasts',
        values,
      });

      const broadcastId = result.data?.id;
      if (!broadcastId) {
        throw new Error('Failed to create broadcast');
      }

      // Start broadcast
      await startBroadcast({
        url: `/broadcasts/${broadcastId}/start`,
        method: 'post',
        values: {},
      });

      message.success('Рассылка создана и запущена!');
      list('broadcasts');
    } catch (error: any) {
      message.error(error?.message || 'Ошибка при создании рассылки');
    } finally {
      setSendingNow(false);
    }
  };

  return (
    <Create
      saveButtonProps={saveButtonProps}
      footerButtons={({ saveButtonProps: defaultSaveProps }) => (
        <Space>
          <Button {...defaultSaveProps}>Сохранить как черновик</Button>
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSaveAndSend}
            loading={sendingNow}
          >
            Сохранить и отправить
          </Button>
        </Space>
      )}
    >
      <Form {...formProps} layout="vertical" initialValues={{ target_type: 'all' }}>
        <Row gutter={24}>
          <Col span={16}>
            <Card title="Содержимое сообщения" style={{ marginBottom: 16 }}>
              <Form.Item
                label="Название рассылки"
                name="name"
                rules={[{ required: true, message: 'Введите название' }]}
              >
                <Input placeholder="Новогодняя акция" />
              </Form.Item>

              <Form.Item
                label="Текст сообщения"
                name="text"
                rules={[{ required: true, message: 'Введите текст сообщения' }]}
                extra="Поддерживается HTML: <b>жирный</b>, <i>курсив</i>, <a href='...'>ссылка</a>"
              >
                <Input.TextArea
                  rows={6}
                  placeholder="Привет! Это сообщение рассылки..."
                  showCount
                  maxLength={4096}
                />
              </Form.Item>

              <Form.Item
                label="Фото"
                name="image_url"
                extra="Загрузите изображение или вставьте URL"
              >
                <ImageUpload />
              </Form.Item>

              <Form.Item
                label="Видео (URL или file_id)"
                name="message_video"
                extra="Опционально"
              >
                <Input placeholder="https://example.com/video.mp4" />
              </Form.Item>

              <Divider>Inline кнопки (опционально)</Divider>
              <Form.List name="buttons">
                {(fields, { add, remove }) => (
                  <>
                    {fields.map(({ key, name, ...restField }) => (
                      <Card key={key} size="small" style={{ marginBottom: 8 }}>
                        <Space direction="vertical" style={{ width: '100%' }}>
                          <Space style={{ display: 'flex' }} align="start">
                            <Form.Item
                              {...restField}
                              name={[name, 'text']}
                              rules={[{ required: true, message: 'Текст кнопки' }]}
                              style={{ marginBottom: 0 }}
                            >
                              <Input placeholder="Текст кнопки" style={{ width: 200 }} />
                            </Form.Item>
                            <Form.Item
                              {...restField}
                              name={[name, 'type']}
                              style={{ marginBottom: 0 }}
                              initialValue="url"
                            >
                              <Select style={{ width: 100 }}>
                                <Select.Option value="url">URL</Select.Option>
                                <Select.Option value="callback">Callback</Select.Option>
                              </Select>
                            </Form.Item>
                            <MinusCircleOutlined onClick={() => remove(name)} style={{ marginTop: 8 }} />
                          </Space>
                          <Form.Item
                            noStyle
                            shouldUpdate={(prev, curr) =>
                              prev.buttons?.[name]?.type !== curr.buttons?.[name]?.type
                            }
                          >
                            {({ getFieldValue }) => {
                              const btnType = getFieldValue(['buttons', name, 'type']) || 'url';
                              return btnType === 'url' ? (
                                <Form.Item
                                  {...restField}
                                  name={[name, 'url']}
                                  style={{ marginBottom: 0 }}
                                  rules={[{ required: true, message: 'Введите URL' }]}
                                >
                                  <Input placeholder="https://example.com" />
                                </Form.Item>
                              ) : (
                                <Form.Item
                                  {...restField}
                                  name={[name, 'callback_data']}
                                  style={{ marginBottom: 0 }}
                                  rules={[{ required: true, message: 'Введите callback_data' }]}
                                  extra="Данные для callback query (до 64 символов)"
                                >
                                  <Input placeholder="action:value" maxLength={64} />
                                </Form.Item>
                              );
                            }}
                          </Form.Item>
                        </Space>
                      </Card>
                    ))}
                    <Form.Item>
                      <Button type="dashed" onClick={() => add({ type: 'url' })} block icon={<PlusOutlined />}>
                        Добавить кнопку
                      </Button>
                    </Form.Item>
                  </>
                )}
              </Form.List>
            </Card>
          </Col>

          <Col span={8}>
            <Card title="Аудитория" style={{ marginBottom: 16 }}>
              <Form.Item
                label="Тип аудитории"
                name="target_type"
                rules={[{ required: true }]}
              >
                <Select onChange={(value) => setTargetType(value)}>
                  <Select.Option value="all">Все пользователи</Select.Option>
                  <Select.Option value="list">Список Telegram ID</Select.Option>
                </Select>
              </Form.Item>

              {targetType === 'list' && (
                <Form.Item
                  label="Telegram ID (через запятую)"
                  name="target_user_ids"
                  extra="Введите ID пользователей"
                  getValueFromEvent={(e) => {
                    const value = e.target.value;
                    if (!value) return [];
                    return value.split(',').map((s: string) => parseInt(s.trim())).filter((n: number) => !isNaN(n));
                  }}
                  getValueProps={(value) => ({
                    value: value?.join(', ') || '',
                  })}
                >
                  <Input.TextArea
                    rows={3}
                    placeholder="123456789, 987654321, ..."
                  />
                </Form.Item>
              )}

              <Form.Item
                label="Боты"
                name="target_bots"
                extra="Оставьте пустым для всех ботов"
              >
                <Select
                  mode="multiple"
                  placeholder="Выберите ботов..."
                  {...botSelectProps}
                  allowClear
                />
              </Form.Item>

              <Form.Item
                label="Языки"
                name="target_languages"
                extra="Оставьте пустым для всех языков"
              >
                <Select
                  mode="multiple"
                  placeholder="Выберите языки..."
                  allowClear
                  options={[
                    { label: 'Русский (ru)', value: 'ru' },
                    { label: 'English (en)', value: 'en' },
                    { label: 'Українська (uk)', value: 'uk' },
                    { label: 'Deutsch (de)', value: 'de' },
                  ]}
                />
              </Form.Item>
            </Card>

            <Card title="Расписание">
              <Form.Item
                label="Время запуска"
                name="scheduled_at"
                extra="Оставьте пустым для сохранения как черновик"
              >
                <DatePicker
                  showTime
                  format="DD.MM.YYYY HH:mm"
                  style={{ width: '100%' }}
                  disabledDate={(current) => current && current < dayjs().startOf('day')}
                  placeholder="Выберите дату и время"
                />
              </Form.Item>
            </Card>
          </Col>
        </Row>
      </Form>
    </Create>
  );
};
