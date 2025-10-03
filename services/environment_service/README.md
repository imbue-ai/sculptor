# Environment Service

## Overview
The Environment Service is responsible for handling environment and image management, as well as isolating any provider-specific implementation details from the rest of the code.

## Architecture

### EnvironmentService
- **DefaultEnvironmentService**: contains the service-layer of EnvironmentService, handling and redirecting any requests to each provider, as well as managing provider startup and cleanup logic.

### Providers
Providers implement specific ways environments and images can be built. Each provider corresponds to an Environment and Image class.
- **DockerProvider**: Manages Docker containers and images
- **LocalProvider**: Handles direct local process execution
- **ModalProvider**: Interfaces with Modal cloud environments
