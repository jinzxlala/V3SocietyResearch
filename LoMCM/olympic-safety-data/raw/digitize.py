from PIL import Image
import numpy as np, json

def run_from(profile, x0, thr, maxgap=2, minlen=8):
    x0=int(round(x0)); n=len(profile); x=x0; end=x0; gap=0
    while x<n:
        if profile[x] < thr:
            end=x; gap=0
        else:
            gap+=1
            if gap>maxgap: break
        x+=1
    L=end-x0+1
    return L if L>=minlen else 0

def digitize(path, x0, px_per_pct, top_cut=30, bot_cut=40):
    a=np.array(Image.open(path).convert("L")).astype(float); H,W=a.shape
    bands=[]; cur=None
    for y in range(H):
        L=run_from(a[y], x0, 200, 2, 15)
        if L>15:
            cur=[y,y] if cur is None else [cur[0],y]
        else:
            if cur is not None: bands.append(tuple(cur)); cur=None
    if cur: bands.append(tuple(cur))
    # drop borders and full-width lines
    keep=[]
    for b in bands:
        mx=max(run_from(a[y],x0,200,2,15) for y in range(b[0],b[1]+1))
        if top_cut < b[0] and b[1] < H-bot_cut and mx < 0.92*(W-x0):
            keep.append(b)
    bands=keep
    full=[b for b in bands if b[1]-b[0]+1>=15]
    if len(full)>=2:
        centers=[(b[0]+b[1])/2 for b in full]
        pitch=float(np.median(np.diff(centers)))
    else:
        pitch=float(np.median([b[1]-b[0]+1 for b in bands])+12)
    thr_merge=0.7*pitch
    rows=[]
    for b in bands:
        if rows and (b[0]-rows[-1][0]) <= thr_merge:
            rows[-1][1]=max(rows[-1][1], b[1])
        else:
            rows.append([b[0], b[1]])
    out=[]
    for yt,yb in rows:
        seg=a[yt:yb+1]
        allL=max(run_from(row, x0, 200, 2, 15) for row in seg)
        inter=seg[3:-3] if yb-yt>=8 else seg
        med=np.median(inter,axis=0)
        grayL=run_from(med, x0, 235, 2, 8)
        blackL=run_from(med, x0, 90, 2, 8)
        out.append(dict(y_top=int(yt), y_bot=int(yb), y_center=(yt+yb)/2.0,
                        all=round(allL/px_per_pct,1), ge1d=round(grayL/px_per_pct,1),
                        gt7d=round(blackL/px_per_pct,1), h=int(yb-yt+1)))
    return out, pitch

def load_labels(tsv, img_h, x_max_frac=0.30):
    labs=[]
    for line in open(tsv):
        p=line.rstrip("\n").split("\t")
        if len(p)<5: continue
        minx,miny,w,h=map(float,p[:4]); txt=p[4]
        if minx>=x_max_frac: continue
        labs.append(dict(y=(1-(miny+h/2))*img_h, h=h*img_h, txt=txt))
    return labs

def attach(rows, labs):
    for r in rows:
        best=None; bd=1e9
        for l in labs:
            d=abs(l["y"]-r["y_center"])
            if d < max(0.75*r["h"], 18) and d<bd: best=l; bd=d
        r["sport"]=best["txt"].strip().rstrip("-• ").strip() if best else ""
    return rows

if __name__=="__main__":
    cfgs=[("rio2016_soligard_fig1_img0.png","rio_fig1_ocr.tsv",214,19.81,1463,"Rio 2016"),
          ("tokyo2020_soligard_fig1_img0.png","tokyo_fig1_ocr.tsv",483,65.48,3336,"Tokyo 2020")]
    for img,tsv,x0,ppp,H,name in cfgs:
        rows,pitch=digitize(f"olympic-safety-data/raw/{img}",x0,ppp)
        rows=attach(rows, load_labels(f"olympic-safety-data/raw/{tsv}",H))
        print(f"===== {name}: {len(rows)} sport rows, pitch={pitch:.1f}px")
        for r in rows:
            print(f"  {r['sport']:<26} all={r['all']:5.1f}%  ge1d={r['ge1d']:5.1f}%  gt7d={r['gt7d']:5.1f}%  (y{r['y_top']}-{r['y_bot']})")
        json.dump(rows, open(f"olympic-safety-data/raw/fig1_{name.split()[0].lower()}.json","w"), ensure_ascii=False, indent=1)
