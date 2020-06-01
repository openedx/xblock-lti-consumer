LTI 1.3 Consumer Class
-

This implements a LTI 1.3 compliant consumer class which is request agnostic and can
be reused in different contexts (XBlock, Django plugin, and even on other frameworks).

This doesn't implement any data storage, just the methods required for handling LTI messages
and Access Tokens.

Features:
- LTI 1.3 Launch with full OIDC flow
- Support for custom parameters claim
- Support for launch presentation claim
- Access token creation

This implementation was based on the following IMS Global Documents:
- LTI 1.3 Core Specification: http://www.imsglobal.org/spec/lti/v1p3/
- IMS Global Security Framework: https://www.imsglobal.org/spec/security/v1p0/
