import { logger } from '@librechat/data-schemas';

export type MkSsoConfig = {
  appId: string;
  appSecret: string;
  accountKey: string;
  accountSecret: string;
  getOauthTokenUrl: string;
  getTokenUrl: string;
  getUserInfoUrl: string;
};

export type MkUserInfo = {
  loginName: string;
  userName: string;
  email: string;
  phonenumber: string;
};

type MkOauthTokenResponse = {
  access_token: string;
};

type MkUserTokenResponse = {
  success: boolean;
  msg?: string;
  data?: {
    token: string;
  };
};

type MkUserInfoResponse = {
  success: boolean;
  msg?: string;
  data?: {
    loginName: string;
    userName: string;
    email: string;
    phonenumber: string;
  };
};

export function getMkSsoConfig(): MkSsoConfig {
  const appId = process.env.MK_SSO_APP_ID;
  const appSecret = process.env.MK_SSO_APP_SECRET;
  const accountKey = process.env.MK_SSO_ACCOUNT_KEY;
  const accountSecret = process.env.MK_SSO_ACCOUNT_SECRET;
  const getOauthTokenUrl = process.env.MK_SSO_GET_OAUTH_TOKEN_URL;
  const getTokenUrl = process.env.MK_SSO_GET_TOKEN_URL;
  const getUserInfoUrl = process.env.MK_SSO_GET_USER_INFO_URL;

  if (!appId || !appSecret || !accountKey || !accountSecret) {
    throw new Error('蓝凌SSO配置缺失: MK_SSO_APP_ID, MK_SSO_APP_SECRET, MK_SSO_ACCOUNT_KEY, MK_SSO_ACCOUNT_SECRET 必须配置');
  }

  if (!getOauthTokenUrl || !getTokenUrl || !getUserInfoUrl) {
    throw new Error('蓝凌SSO接口地址缺失: MK_SSO_GET_OAUTH_TOKEN_URL, MK_SSO_GET_TOKEN_URL, MK_SSO_GET_USER_INFO_URL 必须配置');
  }

  return {
    appId,
    appSecret,
    accountKey,
    accountSecret,
    getOauthTokenUrl,
    getTokenUrl,
    getUserInfoUrl,
  };
}

export async function getMkOauthToken(config: MkSsoConfig): Promise<string> {
  try {
    const response = await fetch(config.getOauthTokenUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        appKey: config.accountKey,
        appSecret: config.accountSecret,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('[getMkOauthToken] HTTP error:', response.status, errorText);
      throw new Error(`蓝凌OAuth Token接口HTTP错误: ${response.status}`);
    }

    const data = (await response.json()) as MkOauthTokenResponse;

    if (!data.access_token) {
      logger.error('[getMkOauthToken] Invalid response:', data);
      throw new Error('蓝凌返回的OAuth Token无效');
    }

    logger.debug('[getMkOauthToken] Successfully obtained OAuth token');
    return data.access_token;
  } catch (error) {
    logger.error('[getMkOauthToken] Failed to get OAuth token:', error);
    throw error;
  }
}

export async function getMkUserToken(
  config: MkSsoConfig,
  mkCode: string,
  oauthToken: string,
): Promise<string> {
  try {
    const url = `${config.getTokenUrl}?access_token=${encodeURIComponent(oauthToken)}`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        appId: config.appId,
        appSecret: config.appSecret,
        code: mkCode,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('[getMkUserToken] HTTP error:', response.status, errorText);
      throw new Error(`蓝凌User Token接口HTTP错误: ${response.status}`);
    }

    const data = (await response.json()) as MkUserTokenResponse;

    if (!data.success) {
      const errorMsg = data.msg || '未知错误';
      logger.error('[getMkUserToken] API returned failure:', errorMsg);
      throw new Error(`蓝凌换取Token失败: ${errorMsg}`);
    }

    if (!data.data?.token) {
      logger.error('[getMkUserToken] Invalid response:', data);
      throw new Error('蓝凌返回的用户Token无效');
    }

    logger.debug('[getMkUserToken] Successfully obtained user token');
    return data.data.token;
  } catch (error) {
    logger.error('[getMkUserToken] Failed to get user token:', error);
    throw error;
  }
}

export async function getMkUserInfo(
  config: MkSsoConfig,
  userToken: string,
  oauthToken: string,
): Promise<MkUserInfo> {
  try {
    const url = `${config.getUserInfoUrl}?access_token=${encodeURIComponent(oauthToken)}`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        token: userToken,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error('[getMkUserInfo] HTTP error:', response.status, errorText);
      throw new Error(`蓝凌UserInfo接口HTTP错误: ${response.status}`);
    }

    const data = (await response.json()) as MkUserInfoResponse;

    if (!data.success) {
      const errorMsg = data.msg || '未知错误';
      logger.error('[getMkUserInfo] API returned failure:', errorMsg);
      throw new Error(`蓝凌获取用户信息失败: ${errorMsg}`);
    }

    if (!data.data) {
      logger.error('[getMkUserInfo] Invalid response:', data);
      throw new Error('蓝凌返回的用户信息无效');
    }

    const userInfo: MkUserInfo = {
      loginName: data.data.loginName || '',
      userName: data.data.userName || '',
      email: data.data.email || '',
      phonenumber: data.data.phonenumber || '',
    };

    logger.info('[getMkUserInfo] Successfully retrieved user info for:', userInfo.loginName);
    return userInfo;
  } catch (error) {
    logger.error('[getMkUserInfo] Failed to get user info:', error);
    throw error;
  }
}