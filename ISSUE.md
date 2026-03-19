# Background

`LtiResourceLinkRequest` and NRPS membership container requires roles claim and must contain at least one role URI from the published role vocabularies.

IMS 1.3 spec lists 3 role vocabularies ([link](https://www.imsglobal.org/spec/lti/v1p3#roles-claim)) but does NOT limit their use to specific cases.
1. System roles
2. Institution roles
3. Context roles

Spec further subdivides each of these into core and non-core URIs and states: `Core roles are those which are most likely to be relevant within LTI and hence vendors should support them by best practice. Vendors may also use the non-core roles, but they may not be widely used`

Table in the image below shows roles supported by some LTI tools vs Open edX.

<img width="930" height="404" alt="Image" src="https://github.com/user-attachments/assets/08492a51-7a33-4c5f-aad8-cfc8f032156a" />


Here are some observations from the table above:

1. All tools support context roles which makes sense because a typical LTI launch happens from within a course and therefore the role of the user in that course is most relevant to the launch.
2. Open edX does NOT support any context roles. This is why integration fails with most of these tools (see [test results](https://openedx.atlassian.net/wiki/spaces/COMM/pages/5985927169/Tools+tested+with+and+status)).
3.  The institution roles that Open edX supports are really context roles because they are tied to a course and not an org.

The following table shows mapping between role URIs from the spec vs roles in Open edX.

| Course role | Current URIs in roles claim |
|---|---|
| Course Admin | `/institution/person#Instructor` (non-core) |
| Course Staff | `/system/person#Administrator` (core)<br>`/institution/person#Instructor` (non-core) |
| Limited Staff | `/system/person#Administrator` (core)<br>`/institution/person#Instructor` (non-core) |
| None | `/institution/person#Student` (core) |
| All other roles | `/institution/person#Student` (core) |


# Proposed way forward

The table below shows current and proposed mapping between Open edX course roles and roles in the spec. Please refer to the spec to get full URIs and other relevant details: https://www.imsglobal.org/spec/lti/v1p3#roles-claim

<img width="1256" height="422" alt="Image" src="https://github.com/user-attachments/assets/4596cd99-68be-40e0-8792-ac751f371ae5" />

