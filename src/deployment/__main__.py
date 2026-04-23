"""Entry point for CDK and service deployment."""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.deployment.cdk_stack import AgentCoreApp

app = AgentCoreApp()
app.synth()
