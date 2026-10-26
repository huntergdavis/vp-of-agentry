"""Compare actual editor pixels with the hint visible/hidden, including a noise control."""
import base64


def measure_placeholder_paint(page, editor, placeholder, prefix, contrast_floor=4.5):
    """Save three element captures; require glyph pixels inside the editor at the contrast floor.

    This measures paint, not DOM presence. Two hidden captures must match so cursor,
    animation, scrolling or unrelated updates cannot masquerade as hint pixels.
    The caller decides whether a failed measurement blocks or is advisory.
    """
    counts = {s: page.locator(s).count() for s in
              ('[role="dialog"]', ':modal', '.modal-backdrop', 'dialog[open]')}
    assert not any(counts.values()), counts
    options = dict(animations='disabled', caret='hide')
    original = placeholder.evaluate('e=>e.style.visibility')
    visible = editor.screenshot(path=str(prefix)+'-visible.png', **options)
    try:
        placeholder.evaluate("e=>e.style.visibility='hidden'")
        hidden = editor.screenshot(path=str(prefix)+'-hidden.png', **options)
        control = editor.screenshot(path=str(prefix)+'-hidden-control.png', **options)
    finally:
        placeholder.evaluate('(e,value)=>e.style.visibility=value', original)
    metrics = page.evaluate("""async ({images, floor}) => {
        const decode=async data=>{
            const img=new Image();img.src='data:image/png;base64,'+data;await img.decode();
            const canvas=document.createElement('canvas');canvas.width=img.width;canvas.height=img.height;
            const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);
            return {width:img.width,height:img.height,data:ctx.getImageData(0,0,img.width,img.height).data};
        };
        const [visible,hidden,control]=await Promise.all(images.map(decode));
        const sameDimensions=[hidden,control].every(x=>x.width===visible.width&&x.height===visible.height);
        if(!sameDimensions)return {sameDimensions,passed:false};
        const lum=(data,i)=>[.2126,.7152,.0722].reduce((n,w,j)=>{
            const v=data[i+j]/255;return n+w*(v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
        },0);
        let changedPixels=0,contrastPixels=0,controlChangedPixels=0,maxContrast=1;
        for(let i=0;i<visible.data.length;i+=4){
            if([0,1,2,3].some(j=>hidden.data[i+j]!==control.data[i+j]))controlChangedPixels++;
            if([0,1,2,3].some(j=>visible.data[i+j]!==hidden.data[i+j])){
                changedPixels++;
                const a=lum(visible.data,i),b=lum(hidden.data,i);
                const contrast=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
                maxContrast=Math.max(maxContrast,contrast);
                if(contrast>=floor)contrastPixels++;
            }
        }
        return {sameDimensions,width:visible.width,height:visible.height,changedPixels,contrastPixels,
            contrastFloor:floor,maxContrast,controlChangedPixels,
            passed:changedPixels>=16&&contrastPixels>=8&&controlChangedPixels===0};
    }""", dict(images=[base64.b64encode(x).decode('ascii') for x in (visible, hidden, control)], floor=contrast_floor))
    return dict(**metrics, dialog_closed=True, dialogCounts=counts,
                captures=[str(prefix)+suffix for suffix in ('-visible.png', '-hidden.png', '-hidden-control.png')])
