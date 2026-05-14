# tools/run_gap_finder.py
import importlib, sys

def main():
    # try import gap_finder from known paths
    mod = None
    for name in ("src.data_01.timescale.operations.gap_finder", "data_01.timescale.operations.gap_finder", "src.data_01.timescale.operations.gap_finder"):
        try:
            mod = importlib.import_module(name)
            print("Imported gap_finder from", name)
            break
        except Exception as e:
            #print("import failed", name, e)
            continue
    if mod is None:
        print("gap_finder 모듈을 찾을 수 없습니다.")
        sys.exit(1)
    GapFinder = getattr(mod, "GapFinder", None)
    if GapFinder:
        try:
            gf = GapFinder()
            if hasattr(gf, "detect_all_and_enqueue"):
                res = gf.detect_all_and_enqueue()
                print("detect_all_and_enqueue returned:", res)
            elif hasattr(gf, "detect_and_enqueue"):
                res = gf.detect_and_enqueue(None)
                print("detect_and_enqueue returned:", res)
            else:
                print("GapFinder에 호출 가능한 메서드가 없습니다.")
        except Exception as e:
            print("GapFinder 실행 예외:", e)
    else:
        # module-level functions?
        if hasattr(mod, "detect_all_and_enqueue"):
            try:
                res = mod.detect_all_and_enqueue()
                print("module detect_all_and_enqueue returned:", res)
            except Exception as e:
                print("module detect_all_and_enqueue 예외:", e)
        else:
            print("gap_finder에 GapFinder/함수 없음")

if __name__ == "__main__":
    main()
