import { SystemRoles } from 'librechat-data-provider';
import { logger } from '@librechat/data-schemas';
import type { IUser, UserMethods } from '@librechat/data-schemas';
import type { MkUserInfo } from './mkSso';

export interface MkSsoUserDeps {
  findUser: UserMethods['findUser'];
  createUser: UserMethods['createUser'];
  updateUser: UserMethods['updateUser'];
}

/**
 * Generate a random password for new SSO users.
 * SSO users don't use password login, but the field is required.
 * @returns A random 32-character alphanumeric password
 */
export function randomPassword(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let password = '';
  for (let i = 0; i < 32; i++) {
    const randomIndex = Math.floor(Math.random() * chars.length);
    password += chars[randomIndex];
  }
  return password;
}

/**
 * Determine the user role based on the MK_SSO_ADMIN_ACCOUNTS whitelist.
 * Admin accounts in the whitelist get ADMIN role, others get USER (or configured default).
 * @param loginName - The login name from MK SSO
 * @returns SystemRoles.ADMIN or SystemRoles.USER
 */
export function getMkSsoUserRole(loginName: string): SystemRoles {
  const adminAccounts = (process.env.MK_SSO_ADMIN_ACCOUNTS || '')
    .split(',')
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);

  if (adminAccounts.includes(loginName.toLowerCase())) {
    return SystemRoles.ADMIN;
  }

  const defaultRole = process.env.MK_SSO_DEFAULT_ROLE as SystemRoles;
  return defaultRole === SystemRoles.ADMIN ? SystemRoles.ADMIN : SystemRoles.USER;
}

/**
 * Resolve MK SSO user: find existing user or create new one.
 * Matching order: username (loginName) first, then email.
 *
 * Role handling:
 * - New users: role determined by getMkSsoUserRole()
 * - Existing users: only upgrade to ADMIN if in whitelist, never downgrade existing ADMIN
 *
 * @param mkUserInfo - User info from MK SSO
 * @param deps - Dependencies (findUser, createUser, updateUser)
 * @returns The resolved user document
 */
export async function resolveMkSsoUser(
  mkUserInfo: MkUserInfo,
  deps: MkSsoUserDeps,
): Promise<IUser> {
  const { findUser, createUser, updateUser } = deps;
  const normalizedUsername = mkUserInfo.loginName.toLowerCase().trim();
  const normalizedEmail = mkUserInfo.email?.toLowerCase().trim();
  const role = getMkSsoUserRole(mkUserInfo.loginName);

  // 1. Try to find user by username (loginName)
  let user = await findUser({ username: normalizedUsername });

  // 2. If not found and email exists, try to find by email
  if (!user && normalizedEmail) {
    user = await findUser({ email: normalizedEmail });
    if (user) {
      logger.info(
        `[mkSsoUser] User ${normalizedUsername} matched by email: ${normalizedEmail}`,
      );
    }
  }

  // 3. If user not found, create new user
  if (!user) {
    const autoCreateEnabled = process.env.MK_SSO_AUTO_CREATE_USER !== 'false';
    if (!autoCreateEnabled) {
      throw new Error('用户不存在且未开启自动创建');
    }

    logger.info(`[mkSsoUser] Creating new user for loginName: ${normalizedUsername}`);

    const newUser = await createUser(
      {
        provider: 'mk-sso',
        username: normalizedUsername,
        email: normalizedEmail || `${normalizedUsername}@sjjk.com.cn`,
        name: mkUserInfo.userName || mkUserInfo.loginName,
        password: randomPassword(),
        role,
        emailVerified: true,
      },
      undefined, // balanceConfig
      true, // disableTTL
      true, // returnUser
    );

    return newUser as IUser;
  }

  // 4. Update existing user with SSO info
  const updateData: Partial<IUser> = {
    provider: 'mk-sso',
    name: mkUserInfo.userName || user.name,
  };

  // Role sync: only upgrade to ADMIN, never downgrade existing ADMIN
  if (role === SystemRoles.ADMIN && user.role !== SystemRoles.ADMIN) {
    logger.info(
      `[mkSsoUser] Upgrading user ${user.username} to ADMIN role (in whitelist)`,
    );
    updateData.role = SystemRoles.ADMIN;
  }

  // Update email if MK provides one and user doesn't have one
  if (normalizedEmail && !user.email) {
    updateData.email = normalizedEmail;
    updateData.emailVerified = true;
  }

  const updatedUser = await updateUser(user._id.toString(), updateData);
  if (!updatedUser) {
    throw new Error(`用户更新失败: ${user._id}`);
  }

  return updatedUser;
}