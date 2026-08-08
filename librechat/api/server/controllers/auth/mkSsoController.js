const { logger } = require('@librechat/data-schemas');
const { setAuthTokens } = require('~/server/services/AuthService');
const {
  getMkSsoConfig,
  getMkOauthToken,
  getMkUserToken,
  getMkUserInfo,
} = require('@librechat/api');
const { resolveMkSsoUser } = require('@librechat/api');
const { findUser, createUser, updateUser } = require('~/models');

/**
 * Get MK SSO configuration
 * Returns whether SSO is enabled, login URL, and app ID
 */
const getMkSsoConfigController = (req, res) => {
  try {
    const enabled = process.env.MK_SSO_ENABLED === 'true';
    const loginUrl = process.env.MK_SSO_LOGIN_URL || '';
    const appId = process.env.MK_SSO_APP_ID || '';

    return res.status(200).json({
      enabled,
      loginUrl,
      appId,
    });
  } catch (error) {
    logger.error('[getMkSsoConfigController]', error);
    return res.status(500).json({ message: 'Something went wrong' });
  }
};

/**
 * MK SSO Callback Controller
 * Handles SSO callback from MK portal:
 * 1. Validates mkCode from request body
 * 2. Calls MK SSO APIs to get user info
 * 3. Matches/creates local user
 * 4. Issues JWT token via setAuthTokens
 * 5. Returns { token, user }
 */
const mkSsoCallbackController = async (req, res) => {
  try {
    const { mkCode } = req.body;

    if (!mkCode) {
      return res.status(400).json({ message: 'mkCode is required' });
    }

    // Get MK SSO config
    const config = getMkSsoConfig();

    // Step 1: Get OAuth token from MK
    const oauthToken = await getMkOauthToken(config);

    // Step 2: Exchange mkCode for user token
    const userToken = await getMkUserToken(config, mkCode, oauthToken);

    // Step 3: Get user info from MK
    const mkUserInfo = await getMkUserInfo(config, userToken, oauthToken);

    // Step 4: Resolve user (find existing or create new)
    const user = await resolveMkSsoUser(mkUserInfo, {
      findUser,
      createUser,
      updateUser,
    });

    // Step 5: Issue JWT token
    const token = await setAuthTokens(user._id, res, null, req);

    // Prepare safe user object (remove sensitive fields)
    const { password: _p, totpSecret: _t, __v, ...safeUser } = user.toObject ? user.toObject() : user;
    safeUser.id = safeUser._id.toString();

    return res.status(200).json({ token, user: safeUser });
  } catch (error) {
    logger.error('[mkSsoCallbackController]', error);

    // Determine appropriate error status
    const errorMessage = error.message || 'SSO登录失败';
    const status = errorMessage.includes('不存在') || errorMessage.includes('缺失')
      ? 400
      : 401;

    return res.status(status).json({ message: errorMessage });
  }
};

module.exports = {
  getMkSsoConfigController,
  mkSsoCallbackController,
};