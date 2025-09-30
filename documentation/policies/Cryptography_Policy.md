# Cryptography Policy

**Document Version:** 1.0  
**Effective Date:** [Current Date]  
**Review Date:** [Current Date + 1 Year]  
**Approved By:** [Management Name]  
**Classification:** Internal

## 1. Purpose and Scope

This Cryptography Policy defines the standards and procedures for cryptographic controls used to protect information within the Reggie SaaS platform. This policy ensures that encryption is implemented consistently and effectively across all systems and data.

### 1.1 Objectives
- Protect data confidentiality and integrity through encryption
- Ensure compliance with industry standards and regulations
- Establish consistent cryptographic practices
- Define key management procedures

### 1.2 Scope
This policy applies to:
- All data at rest in Google Cloud Platform
- All data in transit between systems
- Encryption keys and certificates
- Cryptographic algorithms and protocols

## 2. Encryption Standards

### 2.1 Data at Rest
- **Algorithm**: AES-256 encryption
- **Key Management**: Google Cloud KMS with customer-managed keys (CMEK)
- **Key Ring**: `storage-key-ring` in `australia-southeast1` region
- **Crypto Key**: `storage-key` for all storage buckets
- **Rotation**: Automatic key rotation enabled

### 2.2 Data in Transit
- **Protocol**: TLS 1.2 or higher
- **Certificate Management**: Google-managed certificates
- **Cipher Suites**: Only approved cipher suites allowed
- **Perfect Forward Secrecy**: Enabled for all connections

### 2.3 Application-Level Encryption
- **Database Fields**: Encrypted fields using `django-cryptography`
- **Sensitive Data**: PII and financial data encrypted at application level
- **Key Storage**: Keys stored in Google Secret Manager

## 3. Key Management

### 3.1 Key Lifecycle
- **Generation**: Keys generated using Google Cloud KMS
- **Distribution**: Keys distributed through secure channels
- **Storage**: Keys stored in Google Cloud KMS
- **Rotation**: Automatic rotation every 90 days
- **Destruction**: Keys securely destroyed when no longer needed

### 3.2 Access Control
- **Key Access**: Limited to authorized service accounts
- **Permissions**: `roles/cloudkms.cryptoKeyEncrypterDecrypter`
- **Service Accounts**:
  - `bh-opie-storage@bh-opie.iam.gserviceaccount.com`
  - `github-actions-production@bh-opie.iam.gserviceaccount.com`
  - `vm-service-account@bh-opie.iam.gserviceaccount.com`

### 3.3 Key Backup and Recovery
- **Backup**: Keys backed up in Google Cloud KMS
- **Recovery**: Recovery procedures documented
- **Testing**: Recovery procedures tested annually

## 4. Cryptographic Algorithms

### 4.1 Approved Algorithms
- **Symmetric Encryption**: AES-256
- **Asymmetric Encryption**: RSA-2048 or higher, ECDSA P-256
- **Hashing**: SHA-256 or higher
- **Digital Signatures**: RSA-2048 or higher, ECDSA P-256

### 4.2 Prohibited Algorithms
- **MD5**: Not allowed for security purposes
- **SHA-1**: Not allowed for digital signatures
- **DES/3DES**: Not allowed
- **RC4**: Not allowed

## 5. Certificate Management

### 5.1 SSL/TLS Certificates
- **Provider**: Google-managed certificates
- **Validation**: Domain validation required
- **Renewal**: Automatic renewal enabled
- **Monitoring**: Certificate expiration monitored

### 5.2 Code Signing
- **Certificates**: Code signing certificates from trusted CA
- **Storage**: Certificates stored in Google Secret Manager
- **Usage**: All production code must be signed

## 6. Implementation Requirements

### 6.1 Storage Buckets
All Google Cloud Storage buckets must use:
- Customer-managed encryption keys (CMEK)
- Uniform bucket-level access
- Access logging enabled
- Versioning enabled

### 6.2 Database
- **Cloud SQL**: Encryption at rest enabled
- **Backups**: Encrypted backups
- **Connections**: TLS-encrypted connections only

### 6.3 Application
- **Environment Variables**: Sensitive data in Google Secret Manager
- **API Keys**: Stored and managed through Secret Manager
- **Configuration**: No hardcoded secrets in code

## 7. Compliance and Monitoring

### 7.1 Compliance Requirements
- **ISO 27001**: Annex A.10.1 - Cryptographic controls
- **GDPR**: Article 32 - Security of processing
- **Industry Standards**: FIPS 140-2 Level 1 or higher

### 7.2 Monitoring
- **Key Usage**: Monitored through Google Cloud KMS
- **Certificate Status**: Monitored for expiration
- **Encryption Status**: Verified through regular audits

## 8. Incident Response

### 8.1 Key Compromise
- **Immediate**: Revoke compromised keys
- **Notification**: Notify security team immediately
- **Investigation**: Conduct forensic investigation
- **Recovery**: Implement new keys and re-encrypt data

### 8.2 Certificate Issues
- **Expiration**: Automatic renewal monitoring
- **Revocation**: Immediate revocation if compromised
- **Replacement**: Issue new certificates immediately

## 9. Training and Awareness

### 9.1 Personnel Training
- **Cryptography Basics**: All personnel trained on encryption concepts
- **Key Management**: Authorized personnel trained on key procedures
- **Incident Response**: Security team trained on crypto incidents

### 9.2 Regular Updates
- **Policy Updates**: Annual policy review and updates
- **Technology Changes**: Updates for new cryptographic standards
- **Threat Landscape**: Updates based on emerging threats

## 10. Policy Violations

Violations of this policy may result in:
- Immediate revocation of cryptographic access
- Disciplinary action up to and including termination
- Legal action if applicable
- Additional security training requirements

## 11. Contact Information

For questions about this policy or cryptographic issues:
- Security Team: security@[company].com
- Key Management: keys@[company].com
- Technical Support: support@[company].com

---

**Document Control:**
- Created: [Date]
- Last Modified: [Date]
- Next Review: [Date + 1 Year]
- Distribution: All Personnel
