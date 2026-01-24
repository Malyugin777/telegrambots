import { useState, useEffect } from 'react';
import { Card, Form, Input, Button, message, Divider, Typography, Space } from 'antd';
import { UserOutlined, MailOutlined, LockOutlined, SaveOutlined } from '@ant-design/icons';
import { useGetIdentity, useLogout } from '@refinedev/core';
import axios from 'axios';

const { Title, Text } = Typography;

interface AdminUser {
  id: number;
  username: string;
  email: string;
  is_superuser: boolean;
  created_at: string;
  last_login: string | null;
}

export const ProfilePage = () => {
  const { data: identity } = useGetIdentity<AdminUser>();
  const { mutate: logout } = useLogout();
  const [profileForm] = Form.useForm();
  const [passwordForm] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [passwordLoading, setPasswordLoading] = useState(false);

  useEffect(() => {
    if (identity) {
      profileForm.setFieldsValue({
        username: identity.username,
        email: identity.email,
      });
    }
  }, [identity, profileForm]);

  const handleUpdateProfile = async (values: { email: string }) => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      await axios.patch(
        '/api/v1/auth/me',
        null,
        {
          params: { email: values.email },
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      message.success('Профиль обновлён');
    } catch (error: any) {
      message.error(error.response?.data?.detail || 'Ошибка обновления профиля');
    }
    setLoading(false);
  };

  const handleChangePassword = async (values: { current_password: string; new_password: string; confirm_password: string }) => {
    if (values.new_password !== values.confirm_password) {
      message.error('Пароли не совпадают');
      return;
    }

    setPasswordLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      await axios.post(
        '/api/v1/auth/me/password',
        null,
        {
          params: {
            current_password: values.current_password,
            new_password: values.new_password,
          },
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      message.success('Пароль изменён');
      passwordForm.resetFields();
    } catch (error: any) {
      message.error(error.response?.data?.detail || 'Ошибка смены пароля');
    }
    setPasswordLoading(false);
  };

  return (
    <div style={{ padding: '24px', maxWidth: '600px', margin: '0 auto' }}>
      <Title level={2}>
        <UserOutlined /> Профиль
      </Title>

      <Card style={{ marginBottom: '24px' }}>
        <Title level={4}>Информация</Title>
        <Form
          form={profileForm}
          layout="vertical"
          onFinish={handleUpdateProfile}
        >
          <Form.Item label="Имя пользователя" name="username">
            <Input prefix={<UserOutlined />} disabled />
          </Form.Item>

          <Form.Item
            label="Email"
            name="email"
            rules={[
              { required: true, message: 'Введите email' },
              { type: 'email', message: 'Некорректный email' },
            ]}
          >
            <Input prefix={<MailOutlined />} />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} icon={<SaveOutlined />}>
              Сохранить
            </Button>
          </Form.Item>
        </Form>

        <Divider />

        <Space direction="vertical">
          <Text type="secondary">
            Роль: {identity?.is_superuser ? 'Суперпользователь' : 'Администратор'}
          </Text>
          {identity?.last_login && (
            <Text type="secondary">
              Последний вход: {new Date(identity.last_login).toLocaleString()}
            </Text>
          )}
        </Space>
      </Card>

      <Card>
        <Title level={4}>
          <LockOutlined /> Сменить пароль
        </Title>
        <Form
          form={passwordForm}
          layout="vertical"
          onFinish={handleChangePassword}
        >
          <Form.Item
            label="Текущий пароль"
            name="current_password"
            rules={[{ required: true, message: 'Введите текущий пароль' }]}
          >
            <Input.Password prefix={<LockOutlined />} />
          </Form.Item>

          <Form.Item
            label="Новый пароль"
            name="new_password"
            rules={[
              { required: true, message: 'Введите новый пароль' },
              { min: 6, message: 'Минимум 6 символов' },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} />
          </Form.Item>

          <Form.Item
            label="Подтверждение пароля"
            name="confirm_password"
            rules={[{ required: true, message: 'Подтвердите пароль' }]}
          >
            <Input.Password prefix={<LockOutlined />} />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={passwordLoading} icon={<SaveOutlined />}>
              Сменить пароль
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default ProfilePage;
