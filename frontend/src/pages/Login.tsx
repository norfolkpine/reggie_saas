import {FormEvent, useContext, useState} from "react";
import {ApiApi, LoginRequest, User} from "api-client"; // Assuming LoginRequest and User type from allauth response
import {getApiConfiguration} from "../api/utils";
import {AuthContext} from "../auth/authcontext";
import { useNavigate } from "react-router-dom";

// Helper to get the API client instance
const getClient = () => {
  return new ApiApi(getApiConfiguration());
};

export default function LoginPage() {
  const { setUserDetails } = useContext(AuthContext); // Renamed to handleLoginSuccess in AuthProvider
  const [ email, changeEmail ] =  useState('');
  const [ password, changePassword ] =  useState('');
  const [ loginError, setLoginError ] =  useState('');
  const navigate = useNavigate();

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoginError(''); // Clear previous errors
    const client = getClient();

    // Construct payload for allauth headless login
    // Allauth typically expects 'login' (can be username or email) and 'password' directly.
    // Or 'email' and 'password'. This depends on allauth's exact API spec for this endpoint.
    // Let's assume it expects an object like `LoginRequest` from the `api-client`
    const loginPayload: LoginRequest = {login: email, password: password}; // Or {email: email, password: password}

    try {
      // Placeholder for the actual generated method, e.g., client.apiAllauthLOGINCreate(loginPayload)
      // The response structure will also be different.
      // Allauth headless login response:
      // - On success: User data, session is set via cookie.
      // - On MFA required: A specific status/response indicating MFA, e.g., { "mfa_required": true, "methods": ["totp"] }
      // - On failure: Error details.
      const response = await client.apiAllauthLOGINCreate({loginRequest: loginPayload}); // Placeholder for actual method and payload structure

      // Assuming 'response.data' contains the body. Actual structure depends on OpenAPI spec and client generation.
      // Let's imagine the response data might look like:
      // { user: User, mfa: false } or { mfa: true, methods: [...] }
      // This is highly speculative and needs to be adjusted to the actual allauth headless API response.

      if (response.mfa && response.mfa.required) { // Hypothetical MFA required response
        // MFA is required, navigate to OTP page.
        // Allauth's MFA flow might not need a temp token stored in localStorage.
        // The session itself might hold the pending MFA state.
        console.log("MFA required, navigating to OTP page");
        navigate('/login/otp/');
      } else if (response.user) { // Hypothetical success response with user data
        setUserDetails(response.user as User); // Pass user data to AuthProvider
        navigate('/');
      } else {
        // Handle other cases or unexpected responses
        setLoginError(response.detail || "Login failed. Please check your credentials.");
      }
    } catch (error: any) {
      console.error("Login error:", error);
      if (error.response && error.response.data) {
        const errorData = error.response.data;
        // Allauth error responses might have a specific structure, e.g. non_field_errors or field specific errors
        if (errorData.non_field_errors && errorData.non_field_errors.length > 0) {
          setLoginError(errorData.non_field_errors.join(" "));
        } else if (errorData.detail) {
          setLoginError(errorData.detail);
        } else {
          setLoginError("An unknown error occurred during login.");
        }
      } else {
        setLoginError("There was a problem logging in. Please try again.");
      }
    }
  }

  return (
    <div className="flex justify-center min-h-screen my-8 ">
      <div className="w-96 px-4 py-4">
        <div>
          <h2 className="mt-6 text-center text-2xl font-bold text-gray-900 dark:text-gray-100">
            Sign In
          </h2>
          <form className="max-w-sm mx-auto" onSubmit={onSubmit}>
            <div className="form-control w-full">
              <label className="label font-bold" htmlFor="email">
                Email
              </label>
              <input type="email" id="email"
                     className="input input-bordered w-full"
                     placeholder="name@example.com" required
                     onChange={(e) => changeEmail(e.target.value)}
                     value={email}
                     name={'email'}/>
            </div>
            <div className="form-control w-full">
              <label className="label font-bold" htmlFor="password">
                Password
              </label>
              <input type="password" id="password"
                     className="input input-bordered w-full"
                     required
                     onChange={(e) => changePassword(e.target.value)}
                     value={password}
                     name={'password'}/>
            </div>
            {loginError ? (
                <p className={"text-xs text-red-500 mt-2"}>{loginError} </p>
            ) : ""}
            <div className="mt-2">
              <button type="submit"
                      className="btn btn-primary btn-block">
                Sign In
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
