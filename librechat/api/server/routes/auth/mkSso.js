const express = require('express');
const { getMkSsoConfigController, mkSsoCallbackController } = require('~/server/controllers/auth/mkSsoController');

const router = express.Router();

/**
 * MK SSO Routes
 */

/**
 * @route GET /config
 * @desc Get MK SSO configuration (enabled, loginUrl, appId)
 * @access Public
 */
router.get('/config', getMkSsoConfigController);

/**
 * @route POST /callback
 * @desc Handle MK SSO callback, exchange mkCode for user token and info
 * @access Public
 */
router.post('/callback', mkSsoCallbackController);

module.exports = router;