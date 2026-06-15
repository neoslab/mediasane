# Contributing to MediaSane

First off, thank you for considering contributing to MediaSane! It's people like you that make this tool better for the entire Ubuntu and Debian-based Linux community.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Code Contributions](#code-contributions)
  - [Documentation Improvements](#documentation-improvements)
  - [Translation & Localization](#translation--localization)
- [Development Setup](#development-setup)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
  - [Branch Naming](#branch-naming)
  - [Commit Messages](#commit-messages)
  - [Code Style Guidelines](#code-style-guidelines)
  - [Testing](#testing)
- [Adding New Features](#adding-new-features)
  - [Adding a New Cleaner Module](#adding-a-new-cleaner-module)
  - [Adding a New Preference Option](#adding-a-new-preference-option)
- [Pull Request Process](#pull-request-process)
- [Getting Help](#getting-help)
- [Recognition](#recognition)

* * *

## Code of Conduct

By participating in this project, you agree to maintain a respectful and constructive environment for everyone. Be kind, professional, and focus on making MediaSane better.

* * *

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the [existing issues](https://github.com/neoslab/mediasane/issues) to avoid duplicates.

**When creating a bug report, include:**

- **Your environment:**
  - Ubuntu/Debian version (`lsb_release -a`)
  - Python version (`python --version`)
  - BlitzSweep version (from DEB or `git describe --tags`)
  - Desktop environment (GNOME, KDE, XFCE, etc.)

- **Steps to reproduce** the issue (be specific)
- **Expected behavior** vs **what actually happened**
- **Screenshots** if applicable
- **Logs or error messages** - run from terminal:
  ```bash
  python main.py 2>&1 | tee mediasane-debug.log