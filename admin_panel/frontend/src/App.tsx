import { Refine, Authenticated } from '@refinedev/core';
import { RefineThemes, ThemedLayoutV2, useNotificationProvider } from '@refinedev/antd';
import routerProvider, {
  NavigateToResource,
  UnsavedChangesNotifier,
  DocumentTitleHandler,
} from '@refinedev/react-router-v6';
import { BrowserRouter, Routes, Route, Outlet, Navigate } from 'react-router-dom';
import { ConfigProvider, App as AntdApp, theme } from 'antd';
import {
  DashboardOutlined,
  RobotOutlined,
  NotificationOutlined,
  UserOutlined,
  FileTextOutlined,
} from '@ant-design/icons';

import { dataProvider } from './providers/dataProvider';
import { authProvider } from './providers/authProvider';

import { Dashboard } from './pages/dashboard';
import { BotList, BotCreate, BotEdit, BotShow } from './pages/bots';
import { BroadcastList, BroadcastCreate, BroadcastEdit, BroadcastShow } from './pages/broadcasts';
import { UserList, UserShow } from './pages/users';
import { LogList } from './pages/activity-logs';
import { Login } from './pages/login';

import '@refinedev/antd/dist/reset.css';

const API_URL = import.meta.env.VITE_API_URL || '/api/v1';

function App() {
  return (
    <BrowserRouter>
      <ConfigProvider
        theme={{
          algorithm: theme.darkAlgorithm,
          token: {
            colorPrimary: '#1890ff',
            borderRadius: 6,
          },
        }}
      >
        <AntdApp>
          <Refine
            routerProvider={routerProvider}
            dataProvider={dataProvider(API_URL)}
            authProvider={authProvider(API_URL)}
            notificationProvider={useNotificationProvider}
            resources={[
              {
                name: 'dashboard',
                list: '/dashboard',
                meta: {
                  label: 'Dashboard',
                  icon: <DashboardOutlined />,
                },
              },
              {
                name: 'bots',
                list: '/bots',
                create: '/bots/create',
                edit: '/bots/edit/:id',
                show: '/bots/show/:id',
                meta: {
                  label: 'Bot Fleet',
                  icon: <RobotOutlined />,
                },
              },
              {
                name: 'broadcasts',
                list: '/broadcasts',
                create: '/broadcasts/create',
                edit: '/broadcasts/edit/:id',
                show: '/broadcasts/show/:id',
                meta: {
                  label: 'Broadcasts',
                  icon: <NotificationOutlined />,
                },
              },
              {
                name: 'users',
                list: '/users',
                show: '/users/show/:id',
                meta: {
                  label: 'Users',
                  icon: <UserOutlined />,
                },
              },
              {
                name: 'logs',
                list: '/logs',
                meta: {
                  label: 'Logs',
                  icon: <FileTextOutlined />,
                },
              },
            ]}
            options={{
              syncWithLocation: true,
              warnWhenUnsavedChanges: true,
            }}
          >
            <Routes>
              <Route
                element={
                  <Authenticated
                    key="authenticated-routes"
                    fallback={<Navigate to="/login" />}
                  >
                    <ThemedLayoutV2
                      Title={() => (
                        <div style={{
                          fontSize: '18px',
                          fontWeight: 'bold',
                          color: '#1890ff',
                          padding: '12px 0'
                        }}>
                          Nexus Control
                        </div>
                      )}
                    >
                      <Outlet />
                    </ThemedLayoutV2>
                  </Authenticated>
                }
              >
                <Route index element={<NavigateToResource resource="dashboard" />} />
                <Route path="/dashboard" element={<Dashboard />} />

                <Route path="/bots">
                  <Route index element={<BotList />} />
                  <Route path="create" element={<BotCreate />} />
                  <Route path="edit/:id" element={<BotEdit />} />
                  <Route path="show/:id" element={<BotShow />} />
                </Route>

                <Route path="/broadcasts">
                  <Route index element={<BroadcastList />} />
                  <Route path="create" element={<BroadcastCreate />} />
                  <Route path="edit/:id" element={<BroadcastEdit />} />
                  <Route path="show/:id" element={<BroadcastShow />} />
                </Route>

                <Route path="/users">
                  <Route index element={<UserList />} />
                  <Route path="show/:id" element={<UserShow />} />
                </Route>

                <Route path="/logs">
                  <Route index element={<LogList />} />
                </Route>
              </Route>

              <Route path="/login" element={<Login />} />
            </Routes>
            <UnsavedChangesNotifier />
            <DocumentTitleHandler />
          </Refine>
        </AntdApp>
      </ConfigProvider>
    </BrowserRouter>
  );
}

export default App;
