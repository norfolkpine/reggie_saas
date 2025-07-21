# Project Privacy and Sharing Design

## Overview
- Projects act as folders for users to organize files.
- By default, projects are **private** to the user who created them (the owner).
- Owners can **share** projects with specific other users (team members).
- Projects may optionally be associated with a team, but user-to-user sharing is the main mechanism.

## Intended Model Changes
- Each `Project` has an `owner` (the creator, a `CustomUser`).
- Each `Project` can have `shared_users` (many-to-many with `CustomUser`).
- Only the owner and users in `shared_users` can see a project.
- Only the owner can update or delete a project.
- Shared users can view (and possibly add files, if desired) but not modify project settings.

## Example Django Model Fields
```python
class Project(BaseModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    owner = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="owned_projects")
    shared_users = models.ManyToManyField(
        CustomUser,
        related_name="shared_projects",
        blank=True,
        help_text="Users this project is shared with."
    )
    # Optionally, for team association:
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="projects",
        null=True,
        blank=True,
        help_text="Team this project belongs to (optional if personal).",
    )
    # ... other fields ...
```

## API/Permissions
- **List/Read:** Owner and shared users can see the project.
- **Update/Delete:** Only the owner can change or remove the project.
- **Create:** New projects are private to the creator by default.
- **Share:** Owner can add users to `shared_users`.

## Example Queryset Restriction (ViewSet)
```python
def get_queryset(self):
    user = self.request.user
    return Project.objects.filter(Q(owner=user) | Q(shared_users=user)).distinct()
```

## Example Serializer Fields
```python
class ProjectSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    shared_users = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all(), many=True, required=False)
    class Meta:
        model = Project
        fields = "__all__"
```

## Summary
This approach ensures projects are private by default, but can be shared with specific users as needed. Team logic can be layered on if desired, but is not required for basic sharing.

## Superadmin Access and ISO Compliance

- Superadmins (system administrators) have the ability to see all projects in both the API and frontend.
- This access is intended for administrative, security, or audit purposes only.
- For ISO/IEC 27001 and similar compliance:
    - Superadmin access to all projects must be justified by business need and documented in the access control policy.
    - All superadmin access to project data should be logged and auditable.
    - Superadmin privileges should be granted sparingly and reviewed regularly.
    - Regular users should never have access to all projects—only their own, shared, or team projects.
- Consider implementing audit logging for all superadmin actions and requiring justification for elevated access.
