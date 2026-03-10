"""Point d'entrée : python -m server"""

import asyncio
from server.main import main

if __name__ == "__main__":
    asyncio.run(main())
