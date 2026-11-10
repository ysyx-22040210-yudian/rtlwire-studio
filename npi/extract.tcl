# NPI adapter. All design objects come from the already-loaded elab database.
proc emit {tag args} {
    set parts [list $tag]
    foreach value $args {
        binary scan [encoding convertto utf-8 $value] H* encoded
        lappend parts $encoded
    }
    puts $::raw [join $parts "\t"]
}
proc ps {p h} {
    if {[catch {npi_nl_get_str -property $p -object $h} v]} {return ""}
    return $v
}
proc pi {p h {default -1}} {
    if {[catch {npi_nl_get -property $p -object $h} v] || ![string is integer -strict $v]} {return $default}
    return $v
}
proc one {typ h} {
    if {[catch {npi_nl_handle -type $typ -refHandle $h} v]} {return ""}
    return $v
}
proc inventory {h parent} {
    set name [ps npiNlFullName $h]
    if {[info exists ::instParent($name)]} {return}
    if {[array size ::instParent] >= $::cfg(max_instances)} {error "INSTANCE_LIMIT: hierarchy inventory incomplete"}
    set ::instParent($name) $parent
    set ::instCell($name) [ps npiNlCellType $h]
    set ::instModule($name) [ps npiNlDefName $h]
    emit I $name $parent $::instModule($name) $::instCell($name)
    if {$::instCell($name) ne "npiNlModuleCell"} {return}
    foreach typ {npiNlPort npiNlNet} {
        set it [npi_nl_iterate -type $typ -refHandle $h]
        while {$it ne "" && [set o [npi_nl_scan -iterator $it]] ne ""} {
            emit S [ps npiNlFullName $o] $name [ps npiNlName $o] [ps npiNlType $o] [ps npiNlDirection $o] [pi npiNlSize $o] [pi npiNlLeft $o] [pi npiNlRight $o]
        }
    }
    set it [npi_nl_iterate -type npiNlInst -refHandle $h]
    while {$it ne "" && [set o [npi_nl_scan -iterator $it]] ne ""} {inventory $o $name}
}
proc within {inst boundary} {
    set seen {}
    while {$inst ne ""} {
        if {$inst eq $boundary} {return 1}
        if {[dict exists $seen $inst] || ![info exists ::instParent($inst)]} {return 0}
        dict set seen $inst 1
        set inst $::instParent($inst)
    }
    return 0
}
proc register_node {h} {
    set typ [ps npiNlType $h]
    set name [ps npiNlFullName $h]
    if {$typ eq "" || $name eq ""} {error "NPI_OBJECT_UNRESOLVED"}
    set l [pi npiNlLeft $h]
    set r [pi npiNlRight $h]
    set size [pi npiNlSize $h]
    set key [list $typ $name $l $r]
    if {[info exists ::ids($key)]} {return $::ids($key)}
    if {$::nodeCount >= $::cfg(max_nodes)} {error "NODE_LIMIT"}
    set id n[incr ::nodeCount]
    set ::ids($key) $id
    set base $h
    if {[string match npiNlPseudo* $typ]} {
        set p [one npiNlParent $h]
        if {$p ne ""} {set base $p}
    }
    set instH [one npiNlInst $h]
    if {$instH eq ""} {set instH [one npiNlInst $base]}
    set inst [ps npiNlFullName $instH]
    set cell [ps npiNlCellType $instH]
    set module [ps npiNlDefName $instH]
    set scope $inst
    if {$cell ne "npiNlModuleCell" && [info exists ::instParent($inst)]} {set scope $::instParent($inst)}
    set ::handles($id) $h
    set ::types($id) $typ
    set ::scopes($id) $scope
    set ::cells($id) $cell
    set ::directions($id) [ps npiNlDirection $h]
    emit N $id $typ $name [ps npiNlName $h] $scope $inst $module $cell $::directions($id) $l $r $size [ps npiNlFullName $base] [ps npiNlType $base] [pi npiNlIsLiteral $h 0]
    return $id
}
proc selected_nodes {name role} {
    set h [::npi_L1::npi_nl_sig_handle_by_name $name]
    if {$h eq ""} {emit U $role $name; return {}}
    set size [pi npiNlSize $h]
    set l [pi npiNlLeft $h]
    set r [pi npiNlRight $h]
    set result {}
    if {$size > $::cfg(max_signal_bits)} {error "SIGNAL_BIT_LIMIT: $name ($size)"}
    if {$size > 1} {
        for {set b [expr {min($l,$r)}]} {$b <= [expr {max($l,$r)}]} {incr b} {
            set bh [npi_nl_handle_by_range -refHandle $h -left $b -right $b]
            if {$bh eq ""} {error "BIT_RESOLVE_FAILED: $name bit $b"}
            set id [register_node $bh]
            emit Q $role $name $id $b
            lappend result $id
        }
    } else {
        set id [register_node $h]
        set bit ""
        if {[string match npiNlPseudo* [ps npiNlType $h]]} {set bit $l}
        emit Q $role $name $id $bit
        lappend result $id
    }
    return $result
}
proc edge {a b kind detail} {
    set key [list $a $b $kind $detail]
    if {![info exists ::edges($key)]} {
        if {[array size ::edges] >= $::cfg(max_edges)} {error "EDGE_LIMIT"}
        set ::edges($key) 1
        emit E $a $b $kind $detail
    }
}
proc stop {reason id direction {detail ""}} {
    set key [list $reason $id $direction $detail]
    if {![info exists ::stops($key)]} {set ::stops($key) 1; emit T $reason $id $direction $detail}
}
proc enqueue_neighbor {id neighbor direction depth kind detail} {
    set nid [register_node $neighbor]
    if {$direction eq "load"} {edge $id $nid $kind $detail} else {edge $nid $id $kind $detail}
    lappend ::queue [list $nid $direction [expr {$depth+1}]]
}
proc explore {} {
    set cursor 0
    while {$cursor < [llength $::queue]} {
        lassign [lindex $::queue $cursor] id dir depth
        incr cursor
        set key [list $id $dir]
        if {[info exists ::visited($key)]} {continue}
        set ::visited($key) 1
        if {![within $::scopes($id) $::cfg(boundary)]} {stop STOP_BOUNDARY $id $dir $::scopes($id); continue}
        if {$depth >= $::cfg(max_depth)} {stop DEPTH_LIMIT $id $dir; continue}
        set h $::handles($id)
        set relation [expr {$dir eq "load" ? "npiNlLoad" : "npiNlDriver"}]
        set size [pi npiNlSize $h]
        if {$size > 1} {
            stop UNSUPPORTED_WIDE_TRANSITION $id $dir
            continue
        }
        set l [pi npiNlLeft $h]
        set r [pi npiNlRight $h]
        if {$l >= 0 && $r >= 0} {
            set it [npi_nl_iterate_with_range -type $relation -refHandle $h -left $l -right $r]
        } else {set it [npi_nl_iterate -type $relation -refHandle $h]}
        while {$it ne "" && [set nh [npi_nl_scan -iterator $it]] ne ""} {
            set nt [ps npiNlType $nh]
            if {$nt eq "npiNlInst"} {continue}
            set kind WIRE
            if {[string match *Port $::types($id)] && [string match *Port $nt]} {set kind HIER_BIND}
            enqueue_neighbor $id $nh $dir $depth $kind $relation
        }
        if {[string match *InstPort $::types($id)] && $::cells($id) ne "npiNlModuleCell"} {
            set expected [expr {$dir eq "load" ? "npiNlInput" : "npiNlOutput"}]
            if {$::directions($id) ne $expected} {
                if {$::directions($id) eq "npiNlInout"} {stop UNSUPPORTED_INOUT_CELL $id $dir}
                continue
            }
            set cell $::cells($id)
            if {[regexp {FlipFlop|Latch|Ram|Memory|FSM} $cell]} {stop STOP_SEQUENTIAL $id $dir $cell; continue}
            set wires {npiNlAssignCell npiNlBufCell}
            set logic {npiNlNegCell npiNlAndCell npiNlOrCell npiNlXorCell npiNlNandCell}
            if {$cell ni $wires && !($::cfg(traversal) eq "dependency" && $cell in $logic)} {
                if {$::cfg(traversal) eq "wire_only" && $cell in $logic} {
                    stop STOP_LOGIC $id $dir $cell
                } else {stop UNSUPPORTED_CELL $id $dir $cell}
                continue
            }
            set other {}
            ::npi_L1::npi_nl_pass_primitive_cell $h other
            if {[llength $other] == 0} {stop UNRESOLVED_CELL_TRANSFER $id $dir $cell}
            foreach oh $other {
                set od [ps npiNlDirection $oh]
                if {$od eq $expected} {continue}
                set kind [expr {$cell in $wires ? "ASSIGN" : "LOGIC_DEP"}]
                enqueue_neighbor $id $oh $dir $depth $kind $cell
            }
        }
    }
}

set ::raw [open $env(RTLWIRE_RAW) w]
fconfigure $::raw -encoding utf-8 -translation lf
set ::nodeCount 0
array set ::instParent {}
array set ::ids {}
array set ::edges {}
array set ::stops {}
array set ::visited {}
set ::queue {}
if {[catch {
    source $env(RTLWIRE_QUERY_TCL)
    debImport -elab $env(RTLWIRE_ELAB_DIR)
    source [file join $env(VERDI_HOME) share NPI L1 TCL npi_L1.tcl]
    schSetPreference -detailRTL on -detailMux on -recogFSM off -expandGenBlock on
    emit M tcl_version [info patchlevel]
    set it [npi_nl_iterate -type npiNlInst -refHandle ""]
    while {$it ne "" && [set h [npi_nl_scan -iterator $it]] ne ""} {inventory $h ""}
    if {[array size ::instParent] == 0} {error "ELAB_LOAD_EMPTY: no elaborated design objects available"}
    if {![info exists ::instParent($::cfg(boundary))]} {error "BOUNDARY_NOT_FOUND: $::cfg(boundary)"}
    foreach name $::cfg(sources) {
        foreach id [selected_nodes $name source] {
            foreach direction $::cfg(directions) {lappend ::queue [list $id $direction 0]}
        }
    }
    explore
    foreach name $::cfg(observe) {selected_nodes $name observe}
    emit Z complete $::nodeCount [array size ::edges]
} message]} {
    emit X $message $::errorInfo
    puts stderr "RTLWIRE_ERROR: $message"
}
close $::raw
debExit
