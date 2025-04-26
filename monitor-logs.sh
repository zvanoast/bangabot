#!/bin/bash

# BangaBot Log Monitoring Script
# Usage: ./monitor-logs.sh [prod|test PR_NUMBER] [options]

set -e

# Colors for better readability
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_usage() {
  echo -e "${YELLOW}Usage:${NC}"
  echo -e "  ${GREEN}./monitor-logs.sh prod${NC}             # Monitor production bot logs"
  echo -e "  ${GREEN}./monitor-logs.sh test <PR_NUMBER>${NC} # Monitor specific PR test bot logs"
  echo -e "\n${YELLOW}Options:${NC}"
  echo -e "  ${BLUE}--follow${NC}      Follow log output (default)"
  echo -e "  ${BLUE}--tail=100${NC}    Show last 100 lines"
  echo -e "  ${BLUE}--db${NC}          Show database logs instead of bot logs"
  echo -e "  ${BLUE}--all${NC}         Show all containers' logs"
}

# Default values
FOLLOW="--follow"
TAIL="--tail=100"
CONTAINER="app" # Default to app container
ALL=false

# Parse environment argument
if [ "$1" == "prod" ]; then
  ENV="prod"
  COMPOSE_FILE="$HOME/bangabot/src/app/docker-compose.yml"
elif [ "$1" == "test" ]; then
  if [ -z "$2" ]; then
    echo -e "${RED}Error: PR number is required for test environment${NC}"
    print_usage
    exit 1
  fi
  ENV="test"
  PR_NUMBER="$2"
  COMPOSE_FILE="$HOME/bangabot_test/pr$PR_NUMBER/docker-compose.pr$PR_NUMBER.yml"
  CONTAINER="bangabot_pr$PR_NUMBER"
  shift # Shift arguments to process options
else
  echo -e "${RED}Error: First argument must be 'prod' or 'test'${NC}"
  print_usage
  exit 1
fi
shift # Shift past the env argument

# Parse additional options
for arg in "$@"; do
  case $arg in
    --tail=*)
      TAIL="$arg"
      ;;
    --no-follow)
      FOLLOW=""
      ;;
    --db)
      if [ "$ENV" == "prod" ]; then
        CONTAINER="db"
      else
        CONTAINER="bangabot_db_pr$PR_NUMBER"
      fi
      ;;
    --all)
      ALL=true
      ;;
    *)
      echo -e "${RED}Unknown option: $arg${NC}"
      print_usage
      exit 1
      ;;
  esac
done

# Check if compose file exists
if [ ! -f "$COMPOSE_FILE" ]; then
  echo -e "${RED}Error: Docker Compose file not found: $COMPOSE_FILE${NC}"
  exit 1
fi

# Display info about what we're monitoring
if [ "$ENV" == "prod" ]; then
  echo -e "${GREEN}Monitoring PRODUCTION environment logs${NC}"
else
  echo -e "${GREEN}Monitoring TEST environment for PR #$PR_NUMBER${NC}"
fi

# Run the log command
if [ "$ALL" = true ]; then
  echo -e "${BLUE}Showing logs for all containers...${NC}"
  sudo docker compose -f "$COMPOSE_FILE" logs $FOLLOW $TAIL
else
  echo -e "${BLUE}Showing logs for container: $CONTAINER${NC}"
  sudo docker compose -f "$COMPOSE_FILE" logs $FOLLOW $TAIL "$CONTAINER"
fi