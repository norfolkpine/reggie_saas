#!/usr/bin/env python
"""
Integration tests for Jira tools

This module contains comprehensive tests for the Jira integration tools.
Run with: python tests/integrations/test_jira_tools.py
"""

import os
import sys
import django
import json

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bh_opie.settings')
django.setup()

from apps.app_integrations.models import NangoConnection
from apps.opie.agents.tools.jira import JiraTools


class JiraToolsTester:
    """Test suite for Jira tools integration"""
    
    def __init__(self):
        self.connection = None
        self.jira_tools = None
        self.setup()
    
    def setup(self):
        """Initialize connection and tools"""
        print("🔍 Setting up Jira Tools Test Suite...")
        
        # Get the connection
        self.connection = NangoConnection.objects.filter(provider='jira').first()
        if not self.connection:
            raise Exception("❌ No Jira connection found")
        
        print(f"Connection ID: {self.connection.connection_id}")
        
        # Initialize JiraTools
        try:
            self.jira_tools = JiraTools(
                connection_id=self.connection.connection_id,
                provider_config_key=self.connection.provider,
                nango_connection=self.connection
            )
            print("✅ JiraTools initialized successfully")
        except Exception as e:
            raise Exception(f"❌ JiraTools initialization failed: {e}")
    
    def test_get_boards(self):
        """Test get_boards functionality"""
        print("\n" + "="*60)
        print("🧪 Testing get_boards...")
        
        try:
            boards = self.jira_tools.get_boards()
            boards_data = json.loads(boards)
            print(f"✅ get_boards successful: {len(boards_data)} boards found")
            
            if boards_data:
                print("Available boards/projects:")
                for i, board in enumerate(boards_data[:5]):  # Show first 5
                    print(f"  {i+1}. {board.get('name', 'Unknown')} ({board.get('key', 'Unknown')})")
                    print(f"     ID: {board.get('id', 'Unknown')}")
                    print(f"     Type: {board.get('projectTypeKey', 'Unknown')}")
                    print()
            return True
        except Exception as e:
            print(f"❌ get_boards failed: {e}")
            return False
    
    def test_search_issues(self):
        """Test search_issues functionality"""
        print("\n" + "="*60)
        print("🧪 Testing search_issues...")
        
        test_queries = [
            ("project is not EMPTY", "All issues"),
            ("project = TAS", "TAS project issues"),
            ("status != Done", "Non-Done issues"),
            ("project = BHCP AND statusCategory != Done", "BHCP open issues"),
            ("assignee = 'Nick'", "Issues assigned to Nick"),
        ]
        
        all_passed = True
        for jql, description in test_queries:
            try:
                print(f"\n  Testing: {description}")
                print(f"  JQL: {jql}")
                
                issues = self.jira_tools.search_issues(jql, max_results=3)
                issues_data = json.loads(issues)
                print(f"  ✅ {len(issues_data)} issues found")
                
                if issues_data:
                    for issue in issues_data[:2]:  # Show first 2
                        print(f"    - {issue.get('key', 'Unknown')}: {issue.get('summary', 'Unknown')}")
                        print(f"      Status: {issue.get('status', 'Unknown')}, Project: {issue.get('project', 'Unknown')}")
                
            except Exception as e:
                print(f"  ❌ Query failed: {e}")
                all_passed = False
        
        return all_passed
    
    def test_get_issue(self):
        """Test get_issue functionality"""
        print("\n" + "="*60)
        print("🧪 Testing get_issue...")
        
        try:
            # First get an issue key from search
            issues = self.jira_tools.search_issues("project is not EMPTY", max_results=1)
            issues_data = json.loads(issues)
            
            if issues_data:
                issue_key = issues_data[0].get('key')
                print(f"  Testing with issue: {issue_key}")
                
                issue = self.jira_tools.get_issue(issue_key)
                issue_data = json.loads(issue)
                print(f"✅ get_issue successful for {issue_key}")
                print(f"  Summary: {issue_data.get('summary', 'Unknown')}")
                print(f"  Status: {issue_data.get('status', 'Unknown')}")
                print(f"  Assignee: {issue_data.get('assignee', 'Unknown')}")
                print(f"  Project: {issue_data.get('project', 'Unknown')}")
                return True
            else:
                print("⚠️  No issues found to test get_issue")
                return False
        except Exception as e:
            print(f"❌ get_issue failed: {e}")
            return False
    
    def test_create_issue(self):
        """Test create_issue functionality"""
        print("\n" + "="*60)
        print("🧪 Testing create_issue...")
        
        try:
            project_key = "TAS"  # Business Admin project
            summary = "Integration Test Issue"
            description = "This is a test issue created during integration testing."
            issuetype = "Task"
            
            print(f"  Creating issue in project: {project_key}")
            print(f"  Summary: {summary}")
            
            result = self.jira_tools.create_issue(project_key, summary, description, issuetype)
            result_data = json.loads(result)
            
            print(f"✅ create_issue result: {result_data.get('status', 'Unknown')}")
            if result_data.get('status') == 'success':
                print(f"  Issue Key: {result_data.get('key', 'Unknown')}")
                print(f"  Issue URL: {result_data.get('url', 'Unknown')}")
                return True
            else:
                print(f"  Error: {result_data.get('error', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"❌ create_issue failed: {e}")
            return False
    
    def test_add_comment(self):
        """Test add_comment functionality"""
        print("\n" + "="*60)
        print("🧪 Testing add_comment...")
        
        try:
            # Use an existing issue
            issues = self.jira_tools.search_issues("project = TAS", max_results=1)
            issues_data = json.loads(issues)
            
            if issues_data:
                issue_key = issues_data[0].get('key')
                comment = "Test comment added during integration testing."
                print(f"  Adding comment to issue: {issue_key}")
                
                result = self.jira_tools.add_comment(issue_key, comment)
                result_data = json.loads(result)
                
                print(f"✅ add_comment result: {result_data.get('status', 'Unknown')}")
                if result_data.get('status') == 'success':
                    print(f"  Comment added successfully")
                    return True
                else:
                    print(f"  Error: {result_data.get('error', 'Unknown error')}")
                    return False
            else:
                print("⚠️  No issues found to test add_comment")
                return False
        except Exception as e:
            print(f"❌ add_comment failed: {e}")
            return False
    
    def test_get_board(self):
        """Test get_board functionality"""
        print("\n" + "="*60)
        print("🧪 Testing get_board...")
        
        try:
            # Get boards first to find a board ID
            boards = self.jira_tools.get_boards()
            boards_data = json.loads(boards)
            
            if boards_data:
                board_id = boards_data[0].get('id')
                print(f"  Testing with board ID: {board_id}")
                
                board = self.jira_tools.get_board(board_id)
                board_data = json.loads(board)
                print(f"✅ get_board successful for board {board_id}")
                print(f"  Board Name: {board_data.get('name', 'Unknown')}")
                print(f"  Board Key: {board_data.get('key', 'Unknown')}")
                print(f"  Board Type: {board_data.get('projectTypeKey', 'Unknown')}")
                return True
            else:
                print("⚠️  No boards found to test get_board")
                return False
        except Exception as e:
            print(f"❌ get_board failed: {e}")
            return False
    
    def test_get_board_issues(self):
        """Test get_board_issues functionality"""
        print("\n" + "="*60)
        print("🧪 Testing get_board_issues...")
        
        try:
            # Use the same board ID from get_board test
            boards = self.jira_tools.get_boards()
            boards_data = json.loads(boards)
            
            if boards_data:
                board_id = boards_data[0].get('id')
                print(f"  Testing with board ID: {board_id}")
                
                issues = self.jira_tools.get_board_issues(board_id, max_results=3)
                issues_data = json.loads(issues)
                print(f"✅ get_board_issues successful: {len(issues_data)} issues found")
                
                if issues_data:
                    print("Sample board issues:")
                    for issue in issues_data[:2]:
                        print(f"  - {issue.get('key', 'Unknown')}: {issue.get('summary', 'Unknown')}")
                return True
            else:
                print("⚠️  No boards found to test get_board_issues")
                return False
        except Exception as e:
            print(f"❌ get_board_issues failed: {e}")
            return False

    def test_get_open_tickets_for_board(self):
        """Test get_open_tickets_for_board functionality"""
        print("\n" + "="*60)
        print("🧪 Testing get_open_tickets_for_board...")
        
        try:
            # Use board 10019 (BH Crypto) for testing
            board_id = "10019"
            print(f"  Testing with board ID: {board_id}")
            
            open_tickets = self.jira_tools.get_open_tickets_for_board(board_id, max_results=5)
            tickets_data = json.loads(open_tickets)
            print(f"✅ get_open_tickets_for_board successful: {len(tickets_data)} open tickets found")
            
            if tickets_data:
                print("Open tickets in board:")
                for ticket in tickets_data[:3]:  # Show first 3
                    print(f"  - {ticket.get('key', 'Unknown')}: {ticket.get('summary', 'Unknown')}")
                    print(f"    Status: {ticket.get('status', 'Unknown')}")
                    print(f"    Assignee: {ticket.get('assignee', 'Unknown')}")
                    print()
            else:
                print("No open tickets found for board")
            return True
        except Exception as e:
            print(f"❌ get_open_tickets_for_board failed: {e}")
            return False

    def test_assign_issue(self):
        """Test assign_issue functionality"""
        print("\n" + "="*60)
        print("🧪 Testing assign_issue...")
        
        try:
            # Get an existing issue to test with
            issues = self.jira_tools.search_issues("project = TAS", max_results=1)
            issues_data = json.loads(issues)
            
            if issues_data:
                issue_key = issues_data[0].get('key')
                print(f"  Testing with issue: {issue_key}")
                
                # Test assignment
                result = self.jira_tools.assign_issue(issue_key, "Nick")
                result_data = json.loads(result)
                print(f"✅ assign_issue result: {result_data.get('status', 'Unknown')}")
                
                if result_data.get('status') == 'success':
                    print(f"  Issue assigned successfully")
                    return True
                else:
                    print(f"  Error: {result_data.get('message', 'Unknown error')}")
                    return False
            else:
                print("⚠️  No issues found to test assign_issue")
                return False
        except Exception as e:
            print(f"❌ assign_issue failed: {e}")
            return False

    def test_update_issue_status(self):
        """Test update_issue_status functionality"""
        print("\n" + "="*60)
        print("🧪 Testing update_issue_status...")
        
        try:
            # Get an existing issue to test with
            issues = self.jira_tools.search_issues("project = TAS", max_results=1)
            issues_data = json.loads(issues)
            
            if issues_data:
                issue_key = issues_data[0].get('key')
                print(f"  Testing with issue: {issue_key}")
                
                # Test status update
                result = self.jira_tools.update_issue_status(issue_key, "In Progress")
                result_data = json.loads(result)
                print(f"✅ update_issue_status result: {result_data.get('status', 'Unknown')}")
                
                if result_data.get('status') == 'success':
                    print(f"  Status updated successfully")
                    return True
                else:
                    print(f"  Error: {result_data.get('message', 'Unknown error')}")
                    return False
            else:
                print("⚠️  No issues found to test update_issue_status")
                return False
        except Exception as e:
            print(f"❌ update_issue_status failed: {e}")
            return False

    def test_update_issue(self):
        """Test update_issue functionality"""
        print("\n" + "="*60)
        print("🧪 Testing update_issue...")
        
        try:
            # Get an existing issue to test with
            issues = self.jira_tools.search_issues("project = TAS", max_results=1)
            issues_data = json.loads(issues)
            
            if issues_data:
                issue_key = issues_data[0].get('key')
                print(f"  Testing with issue: {issue_key}")
                
                # Test field update
                fields_to_update = {
                    "summary": f"Test update - {issue_key}",
                    "priority": "Medium"
                }
                result = self.jira_tools.update_issue(issue_key, fields_to_update)
                result_data = json.loads(result)
                print(f"✅ update_issue result: {result_data.get('status', 'Unknown')}")
                
                if result_data.get('status') == 'success':
                    print(f"  Fields updated successfully: {result_data.get('updated_fields', [])}")
                    return True
                else:
                    print(f"  Error: {result_data.get('message', 'Unknown error')}")
                    return False
            else:
                print("⚠️  No issues found to test update_issue")
                return False
        except Exception as e:
            print(f"❌ update_issue failed: {e}")
            return False

    def run_all_tests(self):
        """Run all tests and return results"""
        print("🚀 Running All Jira Integration Tests...")
        print("="*60)
        
        tests = [
            ("get_boards", self.test_get_boards),
            ("search_issues", self.test_search_issues),
            ("get_issue", self.test_get_issue),
            ("create_issue", self.test_create_issue),
            ("add_comment", self.test_add_comment),
            ("get_board", self.test_get_board),
            ("get_board_issues", self.test_get_board_issues),
            ("get_open_tickets_for_board", self.test_get_open_tickets_for_board),
            ("assign_issue", self.test_assign_issue),
            ("update_issue_status", self.test_update_issue_status),
            ("update_issue", self.test_update_issue),
        ]
        
        results = {}
        for test_name, test_func in tests:
            try:
                results[test_name] = test_func()
            except Exception as e:
                print(f"❌ {test_name} test crashed: {e}")
                results[test_name] = False
        
        # Summary
        print("\n" + "="*60)
        print("📊 Test Results Summary:")
        passed = sum(1 for result in results.values() if result)
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"  {test_name}: {status}")
        
        print(f"\nOverall: {passed}/{total} tests passed")
        return results


def main():
    """Main test runner"""
    try:
        tester = JiraToolsTester()
        results = tester.run_all_tests()
        
        # Exit with error code if any tests failed
        if not all(results.values()):
            sys.exit(1)
    except Exception as e:
        print(f"❌ Test suite failed to initialize: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
