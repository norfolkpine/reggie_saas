# Mobile Authentication Testing Guide

This document provides comprehensive testing instructions for the mobile authentication system in Opie SaaS.

## Overview

The mobile authentication system supports both mobile-specific endpoints and standard JWT authentication. Mobile apps should use the mobile-specific endpoints for enhanced security and validation.

## Available Endpoints

### Mobile App Authentication (Recommended for iPhone/Android Apps)

- `POST /api/auth/mobile/login/` - Mobile app login
- `POST /api/auth/mobile/token/refresh/` - Mobile app token refresh

### Standard JWT Authentication

- `POST /api/auth/jwt/token/` - Standard JWT login
- `POST /api/auth/jwt/token/refresh/` - Standard JWT refresh

## Testing Setup

### 1. Start the Development Server

```bash
source venv/bin/activate
python manage.py runserver
```

### 2. Create a Test User

```bash
source venv/bin/activate
python manage.py shell -c "from apps.users.models import CustomUser; CustomUser.objects.create_user('testuser', 'test@example.com', 'testpass123') if not CustomUser.objects.filter(email='test@example.com').exists() else print('User already exists')"
```

## Mobile App Authentication Testing

### 1. Successful Login

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/auth/mobile/login/ \
  -H "Content-Type: application/json" \
  -H "X-Mobile-App-ID: com.benheath.opie.ios" \
  -H "X-Mobile-App-Version: 1.0.0" \
  -H "X-Device-ID: test-device-123" \
  -d '{"email": "test@example.com", "password": "testpass123"}'
```

**Expected Response:**
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "email": "test@example.com",
    "first_name": "",
    "last_name": "",
    "is_active": true
  },
  "app_info": {
    "app_id": "com.benheath.opie.ios",
    "app_version": "1.0.0",
    "device_id": "test-device-123"
  }
}
```

### 2. Token Refresh

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/auth/mobile/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh": "your_refresh_token_here"}'
```

**Expected Response:**
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### 3. Invalid Mobile App ID

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/auth/mobile/login/ \
  -H "Content-Type: application/json" \
  -H "X-Mobile-App-ID: invalid.app.id" \
  -H "X-Mobile-App-Version: 1.0.0" \
  -H "X-Device-ID: test-device-123" \
  -d '{"email": "test@example.com", "password": "testpass123"}'
```

**Expected Response:**
```json
{
  "error": "Invalid mobile app identifier"
}
```

### 4. Invalid Credentials

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/auth/mobile/login/ \
  -H "Content-Type: application/json" \
  -H "X-Mobile-App-ID: com.benheath.opie.ios" \
  -H "X-Mobile-App-Version: 1.0.0" \
  -H "X-Device-ID: test-device-123" \
  -d '{"email": "test@example.com", "password": "wrongpassword"}'
```

**Expected Response:**
```json
{
  "error": "Invalid credentials"
}
```

### 5. Missing Required Headers

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/auth/mobile/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "testpass123"}'
```

**Expected Response:**
```json
{
  "error": "Invalid mobile app identifier"
}
```

### 6. Missing Required Fields

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/auth/mobile/login/ \
  -H "Content-Type: application/json" \
  -H "X-Mobile-App-ID: com.benheath.opie.ios" \
  -H "X-Mobile-App-Version: 1.0.0" \
  -H "X-Device-ID: test-device-123" \
  -d '{"email": "test@example.com"}'
```

**Expected Response:**
```json
{
  "error": "Email and password are required"
}
```

## Standard JWT Authentication Testing

### 1. Successful Login

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/auth/jwt/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "testpass123"}'
```

**Expected Response:**
```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### 2. Token Refresh

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/auth/jwt/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh": "your_refresh_token_here"}'
```

**Expected Response:**
```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

## Using Access Tokens

Once you have an access token, you can use it to authenticate API requests:

```bash
curl -X GET http://127.0.0.1:8000/api/your-endpoint/ \
  -H "Authorization: Bearer your_access_token_here"
```

## iOS App Integration Example

```swift
import Foundation

class OpieAuthService {
    private let baseURL = "http://127.0.0.1:8000"
    
    func login(email: String, password: String, completion: @escaping (Result<AuthResponse, Error>) -> Void) {
        let url = URL(string: "\(baseURL)/api/auth/mobile/login/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("com.benheath.opie.ios", forHTTPHeaderField: "X-Mobile-App-ID")
        request.setValue("1.0.0", forHTTPHeaderField: "X-Mobile-App-Version")
        request.setValue(UIDevice.current.identifierForVendor?.uuidString ?? "unknown", forHTTPHeaderField: "X-Device-ID")
        
        let body = [
            "email": email,
            "password": password
        ]
        
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        } catch {
            completion(.failure(error))
            return
        }
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            guard let data = data else {
                completion(.failure(NSError(domain: "No data", code: -1)))
                return
            }
            
            do {
                let authResponse = try JSONDecoder().decode(AuthResponse.self, from: data)
                completion(.success(authResponse))
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }
    
    func refreshToken(refreshToken: String, completion: @escaping (Result<RefreshResponse, Error>) -> Void) {
        let url = URL(string: "\(baseURL)/api/auth/mobile/token/refresh/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = ["refresh": refreshToken]
        
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        } catch {
            completion(.failure(error))
            return
        }
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            guard let data = data else {
                completion(.failure(NSError(domain: "No data", code: -1)))
                return
            }
            
            do {
                let refreshResponse = try JSONDecoder().decode(RefreshResponse.self, from: data)
                completion(.success(refreshResponse))
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }
}

// Response models
struct AuthResponse: Codable {
    let access: String
    let refresh: String
    let user: UserInfo
    let appInfo: AppInfo
    
    enum CodingKeys: String, CodingKey {
        case access, refresh, user
        case appInfo = "app_info"
    }
}

struct RefreshResponse: Codable {
    let access: String
    let refresh: String
}

struct UserInfo: Codable {
    let id: Int
    let email: String
    let firstName: String
    let lastName: String
    let isActive: Bool
    
    enum CodingKeys: String, CodingKey {
        case id, email
        case firstName = "first_name"
        case lastName = "last_name"
        case isActive = "is_active"
    }
}

struct AppInfo: Codable {
    let appId: String
    let appVersion: String
    let deviceId: String
    
    enum CodingKeys: String, CodingKey {
        case appId = "app_id"
        case appVersion = "app_version"
        case deviceId = "device_id"
    }
}
```

## Security Features

### Mobile App Validation
- Only accepts requests from registered mobile apps
- Valid app IDs: `com.benheath.opie.ios`, `com.benheath.opie.android`
- Requires `X-Mobile-App-ID` header

### Rate Limiting
- Maximum 5 login attempts per device/IP
- 5-minute timeout for failed attempts
- Prevents brute force attacks

### Input Validation
- Validates email format
- Requires all mandatory fields
- Sanitizes input data

### JWT Token Security
- Access tokens expire in 24 hours
- Refresh tokens expire in 30 days
- Tokens are rotated on refresh
- Blacklist support for revoked tokens

### User Activity Logging
- Logs successful mobile logins
- Tracks device information
- Monitors authentication patterns

## Error Handling

### Common Error Responses

| Error | Status Code | Description |
|-------|-------------|-------------|
| `Invalid mobile app identifier` | 401 | Invalid or missing mobile app ID |
| `Invalid credentials` | 401 | Wrong email/password combination |
| `Email and password are required` | 400 | Missing required fields |
| `Invalid email format` | 400 | Malformed email address |
| `Too many login attempts` | 429 | Rate limit exceeded |
| `Account is disabled` | 401 | User account is inactive |

### Testing Error Scenarios

1. **Invalid Mobile App ID**
2. **Missing Required Headers**
3. **Invalid Credentials**
4. **Missing Required Fields**
5. **Invalid Email Format**
6. **Rate Limiting**
7. **Disabled User Account**

## Production Considerations

### Environment Variables
```bash
# Mobile App Settings
MOBILE_APP_IDS=com.benheath.opie.ios,com.benheath.opie.android
MOBILE_APP_MIN_VERSION=1.0.0

# JWT Settings
SIMPLE_JWT_SIGNING_KEY=your-secure-signing-key
JWT_AUTH_SECURE=True
JWT_AUTH_SAMESITE=Lax
```

### Security Best Practices
1. Use HTTPS in production
2. Store tokens securely on mobile devices
3. Implement token refresh logic
4. Monitor authentication logs
5. Regular security audits
6. Keep mobile app versions updated

## Troubleshooting

### Common Issues

1. **"Address already in use"**
   - Kill existing Django server: `pkill -f runserver`
   - Or use different port: `python manage.py runserver 8001`

2. **Database connection issues**
   - Ensure PostgreSQL is running
   - Check Docker containers: `docker ps`

3. **Import errors**
   - Activate virtual environment: `source venv/bin/activate`
   - Install dependencies: `pip install -r requirements/requirements.txt`

4. **Mobile app ID validation fails**
   - Check `MOBILE_APP_IDS` setting
   - Verify header format: `X-Mobile-App-ID`

### Debug Mode
Enable debug logging for authentication:
```python
LOGGING = {
    'loggers': {
        'rest_framework_simplejwt': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    }
}
```

## API Documentation

For complete API documentation, visit:
- Swagger UI: `http://127.0.0.1:8000/api/schema/swagger-ui/`
- ReDoc: `http://127.0.0.1:8000/api/schema/redoc/`

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review server logs
3. Test with curl commands
4. Contact the development team
