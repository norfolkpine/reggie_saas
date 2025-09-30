# Access Control Policy

**Document Version:** 1.0  
**Effective Date:** [Current Date]  
**Review Date:** [Current Date + 1 Year]  
**Approved By:** [Management Name]  
**Classification:** Internal

## 1. Purpose and Scope

This Access Control Policy establishes the framework for managing user access to information systems and data within the Reggie SaaS platform. This policy ensures that access is granted based on business needs and follows the principle of least privilege.

### 1.1 Objectives
- Control access to information systems and data
- Implement role-based access control (RBAC)
- Ensure compliance with security requirements
- Monitor and audit access activities

### 1.2 Scope
This policy applies to:
- All users, administrators, and service accounts
- Information systems and applications
- Data storage and processing systems
- Network and infrastructure resources

## 2. Access Control Principles

### 2.1 Principle of Least Privilege
- Users receive minimum access necessary for job functions
- Access granted based on business justification
- Regular review and removal of unnecessary access
- Temporary access for specific projects or tasks

### 2.2 Need-to-Know Basis
- Access granted only when required for business functions
- Information shared only with authorized personnel
- Regular review of access requirements
- Immediate revocation when no longer needed

### 2.3 Separation of Duties
- Critical functions require multiple approvals
- No single person has complete control
- Regular rotation of sensitive roles
- Independent review of access decisions

## 3. User Access Management

### 3.1 User Registration
- **New Users**: Formal registration process required
- **Identity Verification**: Email verification mandatory
- **Background Checks**: Required for privileged access
- **Access Request**: Formal approval process

### 3.2 Access Provisioning
- **Role Assignment**: Based on job function and responsibilities
- **Access Levels**: Standard, privileged, administrative
- **Resource Access**: Specific systems and data
- **Time Limits**: Temporary access with expiration

### 3.3 Access Review
- **Quarterly Reviews**: Regular access assessment
- **Annual Audits**: Comprehensive access review
- **Change Management**: Access modifications tracked
- **Documentation**: All access decisions recorded

### 3.4 Access Revocation
- **Immediate Revocation**: Upon termination or role change
- **Scheduled Revocation**: For temporary access
- **Emergency Revocation**: For security incidents
- **Documentation**: All revocations recorded

## 4. Role-Based Access Control

### 4.1 User Roles
- **ROLE_ADMIN**: Full system access and administration
- **ROLE_MEMBER**: Standard user access
- **ROLE_VIEWER**: Read-only access
- **ROLE_GUEST**: Limited access for external users

### 4.2 Service Account Roles
- **bh-opie-storage**: Storage bucket administration
- **github-actions-production**: CI/CD operations
- **vm-service-account**: VM operations
- **cloud-storage-backup**: Backup operations

### 4.3 Permission Levels
- **Read**: View data and reports
- **Write**: Create and modify data
- **Delete**: Remove data and records
- **Admin**: Full system administration

## 5. Authentication and Authorization

### 5.1 Authentication Methods
- **Multi-Factor Authentication**: Required for all users
- **Single Sign-On**: Integration with identity providers
- **API Keys**: For system-to-system authentication
- **Service Accounts**: For automated processes

### 5.2 Password Requirements
- **Minimum Length**: 12 characters
- **Complexity**: Mixed case, numbers, special characters
- **History**: Cannot reuse last 12 passwords
- **Expiration**: 90 days maximum
- **Lockout**: 5 failed attempts

### 5.3 Session Management
- **Session Timeout**: 30 minutes of inactivity
- **Concurrent Sessions**: Limited to 3 sessions
- **Session Monitoring**: Track active sessions
- **Secure Logout**: Proper session termination

## 6. Infrastructure Access Control

### 6.1 Google Cloud Platform
- **IAM Roles**: Granular permission assignment
- **Service Accounts**: Limited scope and permissions
- **Resource-Level Access**: Bucket and project-specific
- **Audit Logging**: All access activities logged

### 6.2 Storage Bucket Access
- **Media Bucket**: User uploads and media files
  - Admin: `bh-opie-storage`, `github-actions-production`
  - Object Admin: `vm-service-account`
  - Users: Authenticated application users

- **Static Bucket**: Django static files
  - Admin: `bh-opie-storage`, `github-actions-production`
  - Object Admin: `vm-service-account`
  - Users: Public read access

- **Docs Bucket**: Customer documents
  - Admin: `bh-opie-storage`, `github-actions-production`
  - Object Admin: `vm-service-account`
  - Users: Authenticated application users

### 6.3 Database Access
- **Application Users**: Limited to application schema
- **Administrators**: Full database access
- **Backup Accounts**: Read-only for backups
- **Monitoring**: Read-only for metrics

## 7. Network Access Control

### 7.1 Firewall Rules
- **SSH Access**: IAP tunnel only (35.235.240.0/20)
- **HTTP/HTTPS**: Internal network only (10.0.1.0/24)
- **Database**: Private network only
- **API Access**: Authenticated users only

### 7.2 CORS Configuration
- **Allowed Origins**: `api.opie.sh`, `app.opie.sh`
- **Methods**: Appropriate HTTP methods per resource
- **Headers**: Standard security headers
- **Credentials**: Secure cookie handling

## 8. Monitoring and Auditing

### 8.1 Access Logging
- **All Access**: Logged to access logs bucket
- **Failed Attempts**: Monitored and alerted
- **Privileged Access**: Enhanced logging
- **API Calls**: Request and response logging

### 8.2 Audit Requirements
- **Regular Reviews**: Quarterly access reviews
- **Compliance Audits**: Annual security assessments
- **Incident Response**: Immediate investigation
- **Documentation**: All findings recorded

### 8.3 Alerting
- **Failed Logins**: Immediate notification
- **Privilege Escalation**: Real-time alerts
- **Unusual Access**: Pattern analysis
- **Security Events**: 24/7 monitoring

## 9. Incident Response

### 9.1 Access Violations
- **Immediate Response**: Revoke access immediately
- **Investigation**: Determine scope and impact
- **Notification**: Alert security team
- **Documentation**: Record all actions

### 9.2 Compromised Accounts
- **Account Lockout**: Immediate suspension
- **Password Reset**: Force password change
- **Session Termination**: Kill all active sessions
- **Forensic Analysis**: Investigate compromise

## 10. Training and Awareness

### 10.1 User Training
- **Access Control**: Basic security principles
- **Password Security**: Strong password practices
- **Phishing Awareness**: Social engineering prevention
- **Incident Reporting**: How to report security issues

### 10.2 Administrator Training
- **Advanced Security**: Privileged access management
- **Audit Procedures**: Access review processes
- **Incident Response**: Security incident handling
- **Compliance Requirements**: Regulatory obligations

## 11. Policy Violations

Violations of this policy may result in:
- Immediate access revocation
- Disciplinary action up to and including termination
- Legal action if applicable
- Additional security training requirements

## 12. Contact Information

For questions about this policy or access issues:
- Security Team: security@[company].com
- IT Support: support@[company].com
- Human Resources: hr@[company].com

---

**Document Control:**
- Created: [Date]
- Last Modified: [Date]
- Next Review: [Date + 1 Year]
- Distribution: All Personnel
