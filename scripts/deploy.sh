#!/bin/bash
# OmniSignal Deployment Script

set -e

echo "🚀 OmniSignal Deployment Script"
echo "================================"
echo ""

# Check if git is initialized
if [ ! -d .git ]; then
    echo "📦 Initializing git repository..."
    git init
    git branch -M main
else
    echo "✓ Git repository already initialized"
fi

# Check for uncommitted changes
if [[ -n $(git status -s) ]]; then
    echo ""
    echo "📝 Staging all changes..."
    git add .
    
    echo ""
    read -p "Enter commit message (default: 'feat: OmniSignal deployment'): " commit_msg
    commit_msg=${commit_msg:-"feat: OmniSignal deployment"}
    
    git commit -m "$commit_msg"
    echo "✓ Changes committed"
else
    echo "✓ No uncommitted changes"
fi

# Check for remote
if ! git remote | grep -q origin; then
    echo ""
    echo "🔗 No remote repository configured"
    read -p "Enter GitHub repository URL (e.g., https://github.com/username/repo.git): " repo_url
    
    if [ -n "$repo_url" ]; then
        git remote add origin "$repo_url"
        echo "✓ Remote added: $repo_url"
    else
        echo "⚠️  Skipping remote setup"
    fi
fi

# Push to GitHub
if git remote | grep -q origin; then
    echo ""
    read -p "Push to GitHub? (y/n): " push_confirm
    
    if [ "$push_confirm" = "y" ]; then
        echo "📤 Pushing to GitHub..."
        git push -u origin main
        echo "✓ Pushed to GitHub"
    fi
fi

echo ""
echo "✅ Deployment preparation complete!"
echo ""
echo "Next steps:"
echo "1. Go to https://vercel.com/new"
echo "2. Import your GitHub repository"
echo "3. Add FRED_API_KEY to environment variables"
echo "4. Deploy!"
echo ""
echo "📖 See DEPLOYMENT.md for detailed instructions"
