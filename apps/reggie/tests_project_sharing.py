from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from apps.users.models import CustomUser # Assuming apps.users.models.CustomUser
from apps.teams.models import Team # Assuming apps.teams.models.Team
from apps.reggie.models import Project

# It's good practice to ensure these models exist or use a flexible way to get the User model
# from django.contrib.auth import get_user_model
# User = get_user_model() # If CustomUser is the AUTH_USER_MODEL

class ProjectSharingTests(APITestCase):
    def setUp(self):
        self.owner_user = CustomUser.objects.create_user(username='owner', email='owner@test.com', password='password123', display_name='Owner User')
        self.member_user = CustomUser.objects.create_user(username='member', email='member@test.com', password='password123', display_name='Member User')
        self.other_user = CustomUser.objects.create_user(username='other', email='other@test.com', password='password123', display_name='Other User')
        self.another_member_user = CustomUser.objects.create_user(username='anothermember', email='anothermember@test.com', password='password123', display_name='Another Member')
        self.superuser = CustomUser.objects.create_superuser(username='superuser', email='superuser@test.com', password='password123')

        # Assuming Team model has 'owner' and 'name' fields.
        # If Team has a direct ManyToMany to User for members, it's often `team.members.add(user)`
        self.team_a = Team.objects.create(name='Team A', owner=self.owner_user)
        self.team_b = Team.objects.create(name='Team B', owner=self.owner_user)

        # Add users to teams
        self.team_a.members.add(self.member_user) # Assuming 'members' is the M2M field on Team to CustomUser
        self.team_b.members.add(self.other_user)


        self.project = Project.objects.create(name='Test Project Alpha', owner=self.owner_user)
        self.project_for_team_share = Project.objects.create(name='Test Project Beta', owner=self.owner_user)

        # URL names might need adjustment based on your router registration.
        # Common pattern for DRF routers is '{basename}-list' for list/create, '{basename}-detail' for retrieve/update/delete
        # and custom actions are often '{basename}-{action_name}'
        self.project_list_url = reverse('project-list') # Standard for list view
        self.project_detail_url = reverse('project-detail', kwargs={'pk': self.project.pk})
        self.add_member_url = reverse('project-add-member', kwargs={'pk': self.project.pk})
        self.remove_member_url = reverse('project-remove-member', kwargs={'pk': self.project.pk})
        self.share_team_url = reverse('project-share-with-team', kwargs={'pk': self.project.pk})
        self.unshare_team_url = reverse('project-unshare-from-team', kwargs={'pk': self.project.pk})


    # --- Test get_queryset (Listing Projects) ---
    def test_owner_can_list_owned_project(self):
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.get(self.project_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, self.project.name)

    def test_member_can_list_project_they_are_member_of(self):
        self.project.members.add(self.member_user)
        self.client.force_authenticate(user=self.member_user)
        response = self.client.get(self.project_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, self.project.name)

    def test_team_member_can_list_project_shared_with_their_team(self):
        self.project.shared_with_teams.add(self.team_a) # member_user is in team_a
        self.client.force_authenticate(user=self.member_user)
        response = self.client.get(self.project_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, self.project.name)

    def test_other_user_cannot_list_unrelated_project(self):
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(self.project_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK) # List view itself is accessible
        self.assertNotContains(response, self.project.name)

    def test_superuser_can_list_all_projects(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(self.project_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, self.project.name)
        self.assertContains(response, self.project_for_team_share.name)

    # --- Test add_member action ---
    def test_owner_can_add_member(self):
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.post(self.add_member_url, {'user_id': self.member_user.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertIn(self.member_user, self.project.members.all())

    def test_non_owner_cannot_add_member(self):
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(self.add_member_url, {'user_id': self.member_user.pk})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_add_non_existent_user_to_project(self):
        self.client.force_authenticate(user=self.owner_user)
        non_existent_user_pk = CustomUser.objects.count() + 999
        response = self.client.post(self.add_member_url, {'user_id': non_existent_user_pk})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_add_member_to_non_existent_project(self):
        self.client.force_authenticate(user=self.owner_user)
        url = reverse('project-add-member', kwargs={'pk': 9999})
        response = self.client.post(url, {'user_id': self.member_user.pk})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- Test remove_member action ---
    def test_owner_can_remove_member(self):
        self.project.members.add(self.member_user)
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.post(self.remove_member_url, {'user_id': self.member_user.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertNotIn(self.member_user, self.project.members.all())

    def test_non_owner_cannot_remove_member(self):
        self.project.members.add(self.member_user)
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(self.remove_member_url, {'user_id': self.member_user.pk})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_remove_non_member_from_project(self):
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.post(self.remove_member_url, {'user_id': self.another_member_user.pk})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST) # Or specific error by view

    # --- Test share_with_team action ---
    def test_owner_can_share_project_with_team(self):
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.post(self.share_team_url, {'team_id': self.team_a.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertIn(self.team_a, self.project.shared_with_teams.all())

    def test_non_owner_cannot_share_project_with_team(self):
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(self.share_team_url, {'team_id': self.team_a.pk})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_share_project_with_non_existent_team(self):
        self.client.force_authenticate(user=self.owner_user)
        non_existent_team_pk = Team.objects.count() + 999
        response = self.client.post(self.share_team_url, {'team_id': non_existent_team_pk})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- Test unshare_from_team action ---
    def test_owner_can_unshare_project_from_team(self):
        self.project.shared_with_teams.add(self.team_a)
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.post(self.unshare_team_url, {'team_id': self.team_a.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertNotIn(self.team_a, self.project.shared_with_teams.all())

    def test_non_owner_cannot_unshare_project_from_team(self):
        self.project.shared_with_teams.add(self.team_a)
        self.client.force_authenticate(user=self.other_user)
        response = self.client.post(self.unshare_team_url, {'team_id': self.team_a.pk})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unshare_project_from_team_not_shared_with(self):
        self.client.force_authenticate(user=self.owner_user)
        # Ensure project is not shared with team_b initially
        self.assertNotIn(self.team_b, self.project.shared_with_teams.all())
        response = self.client.post(self.unshare_team_url, {'team_id': self.team_b.pk})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST) # Or specific error

    def test_add_member_missing_user_id(self):
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.post(self.add_member_url, {}) # Missing user_id
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_remove_member_missing_user_id(self):
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.post(self.remove_member_url, {}) # Missing user_id
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_share_with_team_missing_team_id(self):
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.post(self.share_team_url, {}) # Missing team_id
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unshare_from_team_missing_team_id(self):
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.post(self.unshare_team_url, {}) # Missing team_id
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # Test for project detail view access (implicitly tests get_queryset for single object)
    def test_owner_can_retrieve_project_detail(self):
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.get(self.project_detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.project.name)

    def test_member_can_retrieve_project_detail(self):
        self.project.members.add(self.member_user)
        self.client.force_authenticate(user=self.member_user)
        response = self.client.get(self.project_detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.project.name)

    def test_team_member_can_retrieve_project_detail_shared_with_team(self):
        self.project.shared_with_teams.add(self.team_a) # member_user is in team_a
        self.client.force_authenticate(user=self.member_user)
        response = self.client.get(self.project_detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.project.name)

    def test_other_user_cannot_retrieve_unrelated_project_detail(self):
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(self.project_detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND) # Detail view should 404 if not found by queryset

    def test_superuser_can_retrieve_any_project_detail(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(self.project_detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.project.name)

```
