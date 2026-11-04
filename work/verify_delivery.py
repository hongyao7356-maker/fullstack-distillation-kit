"""v1.1 compatibility entry. Default: read-only verify; export is explicit."""
import sys
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'fullstack-kit/scripts'))
from delivery import main
if __name__=='__main__':raise SystemExit(main())
