#!/usr/bin/env python3
"""
Production validation script to catch placeholder values before deployment.

This script implements fail-fast validation that will prevent the application
from starting if any placeholder/mock values are detected in production configuration.
"""

import os
import sys
import re
from typing import List, Dict, Any
from pathlib import Path

class ProductionValidationError(Exception):
    """Raised when production validation fails."""
    pass

class ProductionValidator:
    """Validates production configuration for placeholders and security issues."""

    # Critical placeholder patterns that will cause failure
    CRITICAL_PATTERNS = [
        r'\byour_.*_key\b',  # Only match 'your_*_key' as whole word, not part of REPLACE_WITH
        r'your-super-secret-key-change-in-production',
        r'admin123',
        r'example\.com',
        r'\blocalhost\b',  # Match localhost as whole word
        r'\b127\.0\.0\.1\b',  # Match IP as whole
        r'\b192\.168\.',  # Match private IP ranges
        r'\b10\.',
        r'\b172\.(1[6-9]|2[0-9]|3[0-1])\.',
    ]

    # Mock class patterns that should not exist in production imports
    MOCK_PATTERNS = [
        r'MockTradingAgent',
        r'MockBinanceFuturesClient',
        r'SimulatedTradingAgent',
        r'AsyncMock.*patch',
    ]

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate_environment_variables(self) -> bool:
        """Validate critical environment variables."""
        print("🔍 Validating environment variables...")

        critical_vars = {
            'BINANCE_API_KEY': r'^your_.*_key$',
            'BINANCE_SECRET_KEY': r'^your_.*_key$',
            'JWT_SECRET_KEY': r'^your-super-secret-key-change-in-production$',
            'ADMIN_PASSWORD': r'^admin123$',
            'DATABASE_URL': r'localhost|127\.0\.0\.1',
        }

        for var_name, forbidden_pattern in critical_vars.items():
            value = os.getenv(var_name)
            if not value:
                self.errors.append(f"❌ CRITICAL: {var_name} is not set")
            elif re.search(forbidden_pattern, value, re.IGNORECASE):
                self.errors.append(f"❌ CRITICAL: {var_name} contains placeholder value: {value}")

        # Check testnet configuration
        binance_testnet = os.getenv('BINANCE_TESTNET', 'false').lower()
        if binance_testnet == 'true':
            environment = os.getenv('ENVIRONMENT', 'development').lower()
            if environment == 'production':
                self.errors.append("❌ CRITICAL: BINANCE_TESTNET=true in production environment")

        return len(self.errors) == 0

    def validate_configuration_files(self) -> bool:
        """Validate configuration files for hardcoded values."""
        print("🔍 Validating configuration files...")

        config_files = [
            '.env',
            '.env.example',
            'docker-compose.yml',
            'src/trading_arena/config.py',
        ]

        for file_path in config_files:
            full_path = Path(file_path)
            if full_path.exists():
                self._scan_file_for_placeholders(full_path)

        return len(self.errors) == 0

    def validate_production_code(self) -> bool:
        """Validate production code for mock imports and TODO items."""
        print("🔍 Validating production code...")

        # Scan Python source files
        src_dir = Path('src/trading_arena')
        if src_dir.exists():
            for py_file in src_dir.rglob('*.py'):
                self._scan_code_file(py_file)

        return len(self.errors) == 0

    def _scan_file_for_placeholders(self, file_path: Path) -> None:
        """Scan a single file for placeholder patterns."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')

            for line_num, line in enumerate(lines, 1):
                for pattern in self.CRITICAL_PATTERNS:
                    matches = re.finditer(pattern, line, re.IGNORECASE)
                    for match in matches:
                        self.errors.append(
                            f"❌ {file_path}:{line_num} - Placeholder found: {match.group()}"
                        )

        except Exception as e:
            self.warnings.append(f"⚠️  Could not scan {file_path}: {e}")

    def _scan_code_file(self, file_path: Path) -> None:
        """Scan Python code for mock imports and TODO items."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')

            for line_num, line in enumerate(lines, 1):
                # Check for mock imports in production code
                for pattern in self.MOCK_PATTERNS:
                    if re.search(pattern, line):
                        # Skip test files
                        if 'test' not in file_path.name.lower():
                            self.errors.append(
                                f"❌ {file_path}:{line_num} - Mock code in production: {line.strip()}"
                            )

                # Check for TODO items in critical paths
                if re.search(r'TODO.*implement', line, re.IGNORECASE):
                    # Allow TODOs in non-critical areas
                    critical_keywords = ['database', 'auth', 'trading', 'api', 'security']
                    if any(keyword in line.lower() for keyword in critical_keywords):
                        self.warnings.append(
                            f"⚠️  {file_path}:{line_num} - Critical TODO: {line.strip()}"
                        )

        except Exception as e:
            self.warnings.append(f"⚠️  Could not scan {file_path}: {e}")

    def run_validation(self) -> bool:
        """Run all validation checks."""
        print("🚀 Starting production validation...")
        print("=" * 50)

        # Detect environment
        environment = os.getenv('ENVIRONMENT', 'development').lower()
        print(f"📝 Environment: {environment}")

        if environment == 'production':
            print("🔒 Running in PRODUCTION mode - strict validation enabled")
        else:
            print("🧪 Running in development mode - reporting issues only")

        print("=" * 50)

        # Run validations
        env_valid = self.validate_environment_variables()
        config_valid = self.validate_configuration_files()
        code_valid = self.validate_production_code()

        # Report results
        print("\n" + "=" * 50)
        print("📊 VALIDATION RESULTS")
        print("=" * 50)

        if self.errors:
            print(f"\n🚨 CRITICAL ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"  {error}")

        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  {warning}")

        if not self.errors and not self.warnings:
            print("\n✅ All validations passed! No placeholders detected.")

        # Final determination
        all_passed = len(self.errors) == 0

        if environment == 'production':
            if not all_passed:
                print("\n❌ PRODUCTION VALIDATION FAILED!")
                print("Fix all critical errors before deploying to production.")
                return False
            else:
                print("\n✅ PRODUCTION VALIDATION PASSED!")
                return True
        else:
            if self.errors:
                print(f"\n⚠️  Found {len(self.errors)} issues that should be fixed before production deployment.")
            return True  # Allow development to continue

def main():
    """Main validation entry point."""
    validator = ProductionValidator()

    try:
        success = validator.run_validation()

        if not success:
            print("\n💥 Deployment blocked due to validation failures.")
            sys.exit(1)
        else:
            print("\n🎉 Validation completed successfully.")
            sys.exit(0)

    except Exception as e:
        print(f"\n💥 Validation failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()