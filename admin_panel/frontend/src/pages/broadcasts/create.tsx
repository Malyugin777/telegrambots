import { Create, useForm, useSelect } from '@refinedev/antd';
import { Form, Input, Select, DatePicker, Card, Row, Col, Divider, Button, Space } from 'antd';
import { PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

export const BroadcastCreate = () => {
  const { formProps, saveButtonProps } = useForm();

  const { selectProps: botSelectProps } = useSelect({
    resource: 'bots',
    optionLabel: 'name',
    optionValue: 'id',
  });

  return (
    <Create saveButtonProps={saveButtonProps}>
      <Form {...formProps} layout="vertical">
        <Row gutter={24}>
          <Col span={16}>
            {/* Main Content */}
            <Card title="Message Content" style={{ marginBottom: 16 }}>
              <Form.Item
                label="Broadcast Name"
                name="name"
                rules={[{ required: true, message: 'Please enter name' }]}
              >
                <Input placeholder="Welcome campaign" />
              </Form.Item>

              <Form.Item
                label="Message Text"
                name="text"
                rules={[{ required: true, message: 'Please enter message text' }]}
                extra="Supports HTML formatting: <b>bold</b>, <i>italic</i>, <code>code</code>"
              >
                <Input.TextArea
                  rows={6}
                  placeholder="Hello! This is your broadcast message..."
                />
              </Form.Item>

              <Form.Item
                label="Image URL"
                name="image_url"
                extra="Optional: URL to an image to attach"
              >
                <Input placeholder="https://example.com/image.jpg" />
              </Form.Item>

              {/* Inline Buttons */}
              <Divider>Inline Buttons (Optional)</Divider>
              <Form.List name="buttons">
                {(fields, { add, remove }) => (
                  <>
                    {fields.map(({ key, name, ...restField }) => (
                      <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="start">
                        <Form.Item
                          {...restField}
                          name={[name, 'text']}
                          rules={[{ required: true, message: 'Enter button text' }]}
                        >
                          <Input placeholder="Button text" style={{ width: 150 }} />
                        </Form.Item>
                        <Form.Item
                          {...restField}
                          name={[name, 'url']}
                        >
                          <Input placeholder="https://link.com" style={{ width: 250 }} />
                        </Form.Item>
                        <MinusCircleOutlined onClick={() => remove(name)} />
                      </Space>
                    ))}
                    <Form.Item>
                      <Button type="dashed" onClick={() => add()} block icon={<PlusOutlined />}>
                        Add Button
                      </Button>
                    </Form.Item>
                  </>
                )}
              </Form.List>
            </Card>
          </Col>

          <Col span={8}>
            {/* Targeting */}
            <Card title="Targeting" style={{ marginBottom: 16 }}>
              <Form.Item
                label="Target Bots"
                name="target_bots"
                extra="Leave empty to send to all bots"
              >
                <Select
                  mode="multiple"
                  placeholder="Select bots..."
                  {...botSelectProps}
                  allowClear
                />
              </Form.Item>

              <Form.Item
                label="Target Languages"
                name="target_languages"
                extra="Leave empty for all languages"
              >
                <Select
                  mode="multiple"
                  placeholder="Select languages..."
                  allowClear
                  options={[
                    { label: 'Russian (ru)', value: 'ru' },
                    { label: 'English (en)', value: 'en' },
                    { label: 'Ukrainian (uk)', value: 'uk' },
                    { label: 'German (de)', value: 'de' },
                    { label: 'French (fr)', value: 'fr' },
                    { label: 'Spanish (es)', value: 'es' },
                  ]}
                />
              </Form.Item>
            </Card>

            {/* Schedule */}
            <Card title="Schedule">
              <Form.Item
                label="Schedule Time"
                name="scheduled_at"
                extra="Leave empty to save as draft"
              >
                <DatePicker
                  showTime
                  format="YYYY-MM-DD HH:mm"
                  style={{ width: '100%' }}
                  disabledDate={(current) => current && current < dayjs().startOf('day')}
                />
              </Form.Item>
            </Card>
          </Col>
        </Row>
      </Form>
    </Create>
  );
};
